# Wiring local ML (M3)

> **Historical integration record.** This page describes how a branch was wired in and is not
> kept up to date: file, class and migration names in it may be stale. For the settings see
> [`docs/guides/settings.md`](../guides/settings.md); for how the app is built today see
> [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).

> **Status (2026-10-02, fix/backend): wired.** Everything here runs in the app: `api/services.py`
> builds it from the one `Settings` and the one `Database`. This page stays as the record of how
> the branch was integrated; where it differs from the code, the code and ARCHITECTURE.md win.

Since fix/backend: the ML store shares the app's `Database` (no connection of its own); the
settings are the `ml` section of `Settings` (env names `PA_ML_*` unchanged); ML jobs are only
planned (after a preview, or by `just ml-backfill`) when the model files are installed.

## 1. What exists

| Layer | Module | What it does |
|---|---|---|
| domain | `vectors.py`, `faces.py` | Vector maths on plain tuples, `Face`/`BoundingBox` (fractions of the displayed image) |
| domain | `clustering.py` | Immich-style incremental clustering: `decide()` per face, `cluster()` as the reference (property-tested) |
| domain | `tags.py` | Vocabulary (18 tags, prompt ensembles), zero-shot tags by margin over a background prototype, screenshot/document flag |
| domain | `search_query.py` | `parse_query("person:Lea date:2023 snow")` → facets + free text |
| ports | `ports/ml.py` | `ImageEmbedder`, `TextEmbedder`, `FaceAnalyzer` (+ `ModelInfo`, `ModelStatus`, `ModelUnavailableError`, `ModelFormatError`), `MlStore` |
| adapters | `onnx_clip.py` | `OnnxClip` (image + text) from an Immich model folder |
| adapters | `faces_insightface.py`, `face_geometry.py` | `InsightFaceAnalyzer` (buffalo_l via onnxruntime; SCRFD decode, NMS, ArcFace alignment) |
| adapters | `faces_opencv.py` | `YuNetSFaceAnalyzer` fallback (OpenCV, Apache-2.0 weights) |
| adapters | `ml_store.py`, `migrations/0020_ml.sql` | `SqliteMlStore`: embeddings, faces, people, tags, per-task status; sqlite-vec KNN |
| app | `ml_jobs.py` | Job handlers `embed_clip`, `detect_faces`, `cluster_faces`, `auto_tag`; `MlJobPlanner` (queue after preview, backfill) |
| app | `search.py`, `people.py` | `SemanticSearch`, `SimilarPhotos`, `People` (list, get, rename, merge, split, assets, faces of an asset) |
| api | `ml_settings.py`, `ml_services.py` | `MlSettings` (`PA_ML_*`), `build_ml_services()` → `MlServices` |
| scripts | `download_models.py` + `just models` | Run on the laptop; downloads into `<data_root>/models/` |

## 2. services.py (composition root)

```python
from photo_assistant.api.ml_services import MlServices, build_ml_services
from photo_assistant.api.ml_settings import MlSettings

@dataclass
class Services:
    ...
    ml: MlServices

    def close(self) -> None:
        self.worker.stop()
        self.ml.close()          # after the worker, before the repo
        self.exiftool.close()
        self.repo.close()

def build_services(settings: Settings) -> Services:
    ...
    ml = build_ml_services(root, MlSettings(), repo, store)   # opens its own DB connection
    worker = Worker(
        repo,
        {
            # ML jobs are queued when the preview exists (they read the 2048 px preview).
            PREVIEW_JOB: ml.planner.after(
                GeneratePreview(repo, store, renderer, settings.preview_edge)
            ),
            SCAN_JOB_KIND: ...,
            **ml.handlers,      # embed_clip, detect_faces, cluster_faces, auto_tag
        },
        clock, poll_seconds=settings.worker_poll_seconds,
    )
```

Nothing loads a model at start-up; the app runs with no model files. Without models each job
ends `done` in the queue and records `model_missing` per asset in `ml_task`.
**After `just models`**, call `services.ml.backfill()` once (route below, or a CLI command
`python -m photo_assistant ml-backfill`). It queues every unfinished (asset, task) plus one
global `cluster_faces {}`. Also queue a global `cluster_faces {}` nightly, or after each
import run, so faces deferred during import (not enough look-alikes yet) get a person later.
A global pass remembers what it saw and next time steps only the deferred faces near a face
that was added or placed since (same people as stepping all of them); the first pass after a
start steps every deferred face once (the memory is the process's, `ClusterFaces`).

Settings: either keep `MlSettings` as its own class (env prefix `PA_ML_`, same `.env`), or
add `ml: MlSettings = Field(default_factory=MlSettings)` to `Settings`. Fields:

| env | default | meaning |
|---|---|---|
| `PA_ML_ENABLED` | `true` | queue ML jobs after import |
| `PA_ML_MODELS_DIR` | `<data_root>/models` | |
| `PA_ML_PROVIDER` | `auto` | `auto` (CUDA if this onnxruntime has it), `cpu`, `cuda` (error if missing) |
| `PA_ML_CLIP_MODEL` | `ViT-B-32__openai` | Immich HF repo name; also the storage key of the vectors |
| `PA_ML_CLIP_BATCH_SIZE` | `16` | |
| `PA_ML_FACE_MODEL` | `buffalo_l` | or `yunet_sface` |
| `PA_ML_FACE_DET_SIZE` | `640` | SCRFD input (dynamic export) / YuNet max edge |
| `PA_ML_FACE_MIN_SCORE` | 0.7 buffalo_l, 0.8 yunet | detection score threshold |
| `PA_ML_FACE_MAX_DISTANCE` | 0.5 buffalo_l, 0.6 yunet | cosine distance for "same person" |
| `PA_ML_FACE_MIN_FACES` | `3` | faces needed to start a person |
| `PA_ML_TAG_MARGIN` / `PA_ML_TAG_MAX_TAGS` | `0.03` / `3` | tune on real photos |
| `PA_ML_SEARCH_MIN_SCORE` | none | drop weak search hits |

## 3. Proposed endpoints

Every route computes `visible = <visibility function>(user)` (M2, repository layer) and
passes it in. The use cases never widen it; ids outside it are 404.

| Method | Path | Body / query | Response | Use case |
|---|---|---|---|---|
| GET | `/api/search` | `q`, `limit` (≤200) + the `/api/assets` filters | `{items: (AssetOut + {score})[], text, facets}` | `parse_query(q)`; facets narrow `visible` (person → `people.assets`, tag → `store.asset_ids_with_tag`, date/place/camera → existing SQL filters); free text → `ml.search(text, candidates, limit)`; no free text → plain filtered timeline. `503 {"detail": "Search needs the CLIP model: run just models"}` on `SearchUnavailableError`. |
| GET | `/api/assets/{id}/similar` | `limit` | `(AssetOut + {score})[]` | `ml.similar(id, viewer, limit)`; `LookupError` → 404, `NotIndexedError` → 409 "not analysed yet" |
| GET | `/api/assets/{id}/faces` | – | `[{id, box:{x,y,w,h}, score, person_id}]` | `people.faces_of_asset` |
| GET | `/api/assets/{id}/tags` | – | `[{name, score}]` + `screen_or_document` | `store.tags_of`, `store.is_screen_or_document` |
| GET | `/api/people` | – | `[{id, name, face_count, asset_count, cover:{face_id, asset_id, box}}]` | `people.list_all(viewer)` |
| GET | `/api/people/{id}` | – | same item | `people.get` |
| PATCH | `/api/people/{id}` | `{name}` | item | `people.rename` (member/admin) |
| POST | `/api/people/{id}/merge` | `{source_ids}` | item | `people.merge` |
| POST | `/api/people/split` | `{face_ids, person_id? , name?}` | item | `people.split` (no `person_id` → new person) |
| GET | `/api/people/{id}/assets` | `limit`, `cursor` | `{items: AssetOut[], next_cursor}` | `people.assets(id, viewer)` (newest first) then the normal timeline query on that page's ids |
| GET | `/api/ml/status` | – | `{clip:{ready,detail}, faces:{ready,detail}, counts:{task:{status:n}}}` | `ml.status()` + `ml_task` counts |
| POST | `/api/ml/backfill` | – | `{queued}` (admin) | `ml.backfill()` |

Face crop thumbnails for the People grid: the web can crop the asset's thumbnail with CSS
using the fractional box, so no new image endpoint is needed at first.
`PersonNotFoundError`/`FaceNotFoundError` → 404, `ValueError` → 422.
"Memories" / On-this-day should exclude `store.screen_or_document_ids(visible)` by default.

## 4. Storage (migration 0020, renumber freely)

Tables: `ml_task`, `clip_embedding`, `face`, `person`, `tag`, `asset_tag`, `asset_ml_flag`.
All reference `asset(id)` with `ON DELETE CASCADE` (trash purge cleans up).

**Deviation from ARCHITECTURE §3 (`vec_clip USING vec0(...)`):** vectors are float32 BLOBs in
ordinary tables, searched with sqlite-vec's `vec_distance_cosine` by brute force within what
the caller may see (`ports.ml.Visible`): a viewer, for whom the store puts the library's access
rule into its own statement, or a set of ids (search, after its filters) held in a temp
candidate table. Reasons: the migration runner uses a plain connection that
can't load extensions; vec0 fixes the dimension per table while the CLIP model (512/640/768/
1024-d) is a setting; and filtering KNN by an arbitrary id set is simpler and exact this way.
At 10k photos this is milliseconds, at 100k well under the 500 ms budget. If it ever isn't,
add a vec0 table per model as an index — the BLOBs are already in vec0's format.

`SqliteMlStore` opens its **own connection** to `library.db` (WAL; its own lock) and loads
sqlite-vec via the Python package. Each embedding row stores `model`, so switching CLIP model
keeps old vectors until a backfill re-embeds (search uses the configured model only).

## 5. Laptop runbook

```
just models                                   # ViT-B-32__openai + buffalo_l (roughly 1 GB)
just models --clip XLM-Roberta-Large-Vit-B-32 # French + English queries; then set
                                              # PA_ML_CLIP_MODEL=XLM-Roberta-Large-Vit-B-32
PA_MODELS_DIR=~/PhotoAssistant/data/models uv run pytest -m models   # format checks
# GPU (RTX 2070): uv pip uninstall onnxruntime && uv pip install onnxruntime-gpu
#   (needs CUDA 12 + cuDNN 9 runtime libraries); status then shows CUDAExecutionProvider.
```
`onnxruntime` and `onnxruntime-gpu` are separate wheels that cannot be installed together, so
the lockfile keeps the CPU one; installing the GPU wheel on the laptop is a manual step
(a `gpu` dependency group would be the tidy follow-up).

Multilingual choice (Immich repo names, check the list on huggingface.co/immich-app):
`XLM-Roberta-Large-Vit-B-32` (M-CLIP, 512-d, large text tower, image tower = ViT-B-32),
`XLM-Roberta-Large-Vit-B-16Plus` (640-d), `nllb-clip-base-siglip__v1` (SigLIP). Benchmark on
our photos (M3 decision in TECH_DECISIONS).

## 6. Model-format assumptions — VERIFY ON THE LAPTOP

These could not be checked here (no access to Hugging Face or GitHub releases). Each one is
guarded by a load-time check that raises `ModelFormatError` naming what it expected and what it
found; `pytest -m models` exercises them.

CLIP (`immich-app/<name>`):
1. Files: `config.json`, `visual/model.onnx`, `visual/preprocess_cfg.json`,
   `textual/model.onnx`, `textual/tokenizer.json`, optional `textual/tokenizer_config.json`.
   Large text towers may come with an external-data file next to `model.onnx` — the script
   downloads every `.onnx_data`/`.data` file under `visual/` and `textual/`.
2. `config.json` has `embed_dim`; context length from `text_cfg.context_length` (default 77).
   If an M-CLIP `config.json` lacks `embed_dim`, loading fails clearly — then read the
   dimension from the model output instead.
3. Visual input: one tensor `[N,3,S,S]` float32, S = `preprocess_cfg.size`; output 0 is
   `[N, embed_dim]`. Batch may be fixed at 1 (then images go one by one).
4. Preprocess: `size` int or `[S,S]`, `mean`/`std` three floats, `resize_mode` `shortest`
   (default) or `squash`. Resize short side to S, centre crop, /255, normalise, CHW, RGB.
   We resize with OpenCV (INTER_AREA when shrinking, CUBIC when enlarging), Immich uses PIL
   bicubic: expect tiny numeric differences, not a different space. Vectors made by Immich
   itself are therefore not interchangeable bit-for-bit (we never mix them).
5. Text inputs: OpenCLIP exports take `text` (int32 or int64) `[N,77]`; M-CLIP takes
   `input_ids` (+ optional `attention_mask`). Any other names → error.
6. Padding: `pad_token` from `tokenizer_config.json` (string or `{"content": ...}`), else
   `<|endoftext|>` or `<pad>`; pad and truncate to the context length. OpenAI CLIP pools at
   the EOT token (highest id), so padding with `<|endoftext|>` after it is harmless.
7. Output is L2-normalised by us regardless of whether the export already does it.

buffalo_l (`insightface v0.7 release buffalo_l.zip`):
8. `det_10g.onnx`: single input `[1,3,?,?]` (dynamic → 640x640) RGB, `(x-127.5)/128`;
   9 outputs = scores `[.,1]`, boxes `[.,4]`, landmarks `[.,10]` for strides 8/16/32 with
   2 anchors per cell, optionally with a leading batch axis. We group outputs **by last
   dimension and row count**, not by order or name. Distances are in stride units.
9. Letterbox top-left with black padding; scale = new_h / h (as insightface).
   NMS IoU 0.4 with the +1-pixel area convention.
10. `w600k_r50.onnx`: input `[N,3,112,112]` RGB `(x-127.5)/127.5` (insightface's rule for
    models without built-in normalisation), output `[N,512]`. Crops aligned by the Umeyama
    similarity onto insightface's `arcface_dst` template (`norm_crop`).
11. Images are decoded by libvips with EXIF orientation applied and fed **RGB** (insightface
    passes BGR with `swapRB=True`, i.e. the network sees RGB too).
12. Faces are detected on the 2048 px preview (thumbnail, then original, as fallbacks), so
    boxes are fractions and very small faces in huge photos may be missed — acceptable for M3.

YuNet + SFace: 2023mar YuNet needs OpenCV ≥ 4.8 (we ship 5.0 headless); rows are
`[x,y,w,h, 10 landmark coords, score]`; SFace gives 128-d. Detection runs on a copy scaled to
`face_det_size` max edge; alignment on the full image. Cluster threshold 0.6 is a guess —
tune on the laptop.

## 7. Known gaps

- Quality signals (FEATURES 2.6, blur/exposure/eyes closed) are not built; landmarks are stored
  (`face.landmarks_json`) for them.
- Real-photo tuning of tag margin, search min score and face thresholds has to happen on the
  laptop (report only aggregate numbers back).
- No cancellation of queued ML jobs when an asset is trashed: handlers treat a missing asset
  as done.
- Embeddings of a previous CLIP model stay in the table after switching; add a cleanup command
  if disk matters (512 floats = 2 KB per photo).
