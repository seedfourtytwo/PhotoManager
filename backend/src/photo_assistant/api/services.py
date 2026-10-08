"""Composition root: the one place that picks real adapters and wires them together."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from photo_assistant.adapters.exiftool_reader import ExifToolReader, ExifToolStripper
from photo_assistant.adapters.filesystem import (
    Blake3Hasher,
    DiskLibraryStore,
    FolderSourceReader,
    SystemClock,
)
from photo_assistant.adapters.geocoder import OfflineGeocoder
from photo_assistant.adapters.passwords import Argon2Hasher
from photo_assistant.adapters.phash import ImageHashPhash
from photo_assistant.adapters.proton_mirror import ProtonMirror
from photo_assistant.adapters.sqlite_database import Database
from photo_assistant.adapters.sqlite_repository import SqliteRepository
from photo_assistant.adapters.typst_print import TypstPrintRenderer
from photo_assistant.adapters.vips_renderer import VipsRenderer
from photo_assistant.api.integrations import Integrations, build_integrations, with_source_areas
from photo_assistant.api.ml_services import MlServices, build_ml_services
from photo_assistant.api.ops_services import OpsServices, RcloneTool, build_ops_services
from photo_assistant.api.settings import Settings
from photo_assistant.app.accounts import Accounts
from photo_assistant.app.album_printer import AlbumPrinter, PrintRenditions
from photo_assistant.app.backup import LONG_JOBS
from photo_assistant.app.derivatives import GeneratePreview
from photo_assistant.app.downloads import Downloads
from photo_assistant.app.editing import RENDER_EDIT_JOB, Editor
from photo_assistant.app.enrich import GEOCODE_JOB, GROUP_JOB, GeocodeAssets, GroupSimilar
from photo_assistant.app.import_source import PREVIEW_JOB, ImportSettings, ImportSource
from photo_assistant.app.ml_jobs import CLUSTER_FACES
from photo_assistant.app.periodic import PeriodicTask
from photo_assistant.app.recheck import ScheduledChecks
from photo_assistant.app.review import Review
from photo_assistant.app.sync_source import SCAN_JOB_KIND
from photo_assistant.app.trash import PURGE_JOB, Trash
from photo_assistant.app.upload import INBOX_RESCAN_SECONDS
from photo_assistant.app.worker import Lanes, StaleJobSweep, new_owner_id
from photo_assistant.domain.access import SESSION_IDLE_LIMIT
from photo_assistant.domain.job_queue import STALE_SWEEP_INTERVAL

# What the daily "prune old records" task keeps (these tables otherwise only grow):
LOGIN_FAILURES_KEPT = timedelta(days=1)  # the lockout itself looks back 15 minutes
AI_LOG_KEPT = timedelta(days=90)  # requests and answers of AI calls, for looking into problems
IMPORT_RUNS_KEPT_IN_DETAIL = 10  # per source: older runs keep their counts, not every file


@dataclass
class Services:
    settings: Settings
    repo: SqliteRepository
    store: DiskLibraryStore
    importer: ImportSource
    worker: Lanes
    exiftool: ExifToolReader
    accounts: Accounts
    editor: Editor
    clock: SystemClock
    downloads: Downloads
    trash: Trash
    review: Review
    integrations: Integrations
    ml: MlServices
    ops: OpsServices
    db: Database  # the one library database: every store shares its writer and lock
    printer: AlbumPrinter
    stale_jobs: StaleJobSweep  # queues jobs again whose process died (server only)
    rechecks: ScheduledChecks

    def enqueue_enrichment(self) -> None:
        """After an import: places and groups for whatever is new (both are idempotent)."""
        self.repo.enqueue_once(GEOCODE_JOB)
        self.repo.enqueue_once(GROUP_JOB)

    def start_background(self) -> None:
        """Server only (never the CLI): the job worker and the periodic housekeeping."""
        self.worker.start()
        self.ops.start()

    def close(self) -> None:
        self.worker.stop()
        self.ops.close()
        self.ml.close()
        self.integrations.ai.close()
        self.exiftool.close()
        self.db.close()


def build_services(settings: Settings, role: str = "cli") -> Services:
    """``role``: what this process is, for the owner id of the jobs it claims (the server
    passes "server"; every command line run is "cli")."""
    root = settings.data_root.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    db = Database.open(root / "library.db", backup_dir=root / "db-backups")
    repo = SqliteRepository(db)
    store = DiskLibraryStore(root)
    renderer = VipsRenderer(concurrency=settings.vips_concurrency)
    exiftool = ExifToolReader()
    clock = SystemClock()
    min_free_bytes = int(settings.min_free_gb * 1000**3)  # one floor: imports and uploads
    importer = ImportSource(
        repo=repo,
        reader=FolderSourceReader(),
        hasher=Blake3Hasher(),
        metadata=exiftool,
        renderer=renderer,
        store=with_source_areas(store, root),  # staging/ and inbox/ live in the data root
        clock=clock,
        settings=ImportSettings(min_free_bytes=min_free_bytes, thumb_edge=settings.thumb_edge),
    )
    trash = Trash(repo, store, clock)
    review = Review(repo, clock)
    stale_jobs = StaleJobSweep(repo, clock)
    integrations = build_integrations(
        data_root=root,
        settings=settings.integrations,
        db=db,
        repo=repo,
        importer=importer,
        clock=clock,
        min_free_bytes=min_free_bytes,
    )
    ml = build_ml_services(root, settings.ml, repo, store, db, on_tags=review.hold_clutter)

    def scan(payload: dict[str, object]) -> object:
        # rclone sources are pulled into staging/ first; every kind is then imported
        outcome = integrations.sync_source.run(int(str(payload["source_id"])))
        repo.enqueue_once(GEOCODE_JOB)
        repo.enqueue_once(GROUP_JOB)
        return outcome

    rechecks = ScheduledChecks(repo, clock)

    def prune_old_records() -> None:
        now = clock.now()
        repo.prune_login_failures(now - LOGIN_FAILURES_KEPT)
        repo.prune_sessions(now - SESSION_IDLE_LIMIT)  # exactly the expired ones
        integrations.ai_log.prune(now - AI_LOG_KEPT)
        repo.prune_import_items(IMPORT_RUNS_KEPT_IN_DETAIL)

    housekeeping = [
        # only queues the scan job of each source whose timer has run out (issues 7 and 8)
        PeriodicTask("due folder checks", settings.source_recheck_poll_seconds, rechecks.queue_due),
        PeriodicTask(
            "trash purge",
            settings.trash_purge_every_hours * 3600,
            lambda: repo.enqueue_once(PURGE_JOB),
        ),
        PeriodicTask(
            "cluster faces",
            settings.face_cluster_every_hours * 3600,
            lambda: repo.enqueue_once(CLUSTER_FACES),
        ),
        PeriodicTask("optimize database", 6 * 3600, repo.optimize),
        PeriodicTask(
            "prune finished jobs",
            24 * 3600,
            lambda: repo.prune_done_jobs(clock.now() - timedelta(days=7)),
        ),
        PeriodicTask("prune old records", 24 * 3600, prune_old_records),
        PeriodicTask(
            "inbox rescan",
            INBOX_RESCAN_SECONDS,
            lambda: integrations.upload.rescan(repo.list_sources(), repo.enqueue_once),
        ),
        PeriodicTask("requeue stale jobs", STALE_SWEEP_INTERVAL.total_seconds(), stale_jobs.run),
    ]
    ops = build_ops_services(
        root,
        settings.ops,
        db=db,
        rclone=RcloneTool(settings.integrations.rclone_binary, settings.integrations.rclone_config),
        queue=repo,
        housekeeping=housekeeping,
        source_roots=lambda: [Path(s.root) for s in repo.list_sources()],
        mirror=ProtonMirror(integrations.proton),
    )
    editor = Editor(
        repo,
        store,
        renderer,
        thumb_edge=settings.thumb_edge,
        preview_edge=settings.preview_edge,
        queue=repo,
    )
    worker = Lanes(
        repo,
        {
            # ML jobs read the preview, so they are planned once it exists
            PREVIEW_JOB: ml.planner.after(
                GeneratePreview(repo, store, renderer, settings.preview_edge, settings.thumb_edge)
            ),
            SCAN_JOB_KIND: scan,  # one handler: pulls rclone sources, then imports any kind
            GEOCODE_JOB: GeocodeAssets(repo, OfflineGeocoder()),
            GROUP_JOB: GroupSimilar(
                repo, ImageHashPhash(), lambda rel: store.absolute(rel), review=review
            ),
            PURGE_JOB: trash.purge_expired,
            RENDER_EDIT_JOB: editor.render_edits,
            **ml.handlers,
            **ops.backup.job_handlers(),
        },
        clock,
        # backups, restore tests and source scans (rclone pulls, whole-folder imports) run on a
        # lane of their own: previews, uploads and the rest never wait behind them (B24)
        long_kinds={SCAN_JOB_KIND, *LONG_JOBS},
        pooled={PREVIEW_JOB: settings.preview_threads()},
        poll_seconds=settings.worker_poll_seconds,
        owner=new_owner_id(role),
    )
    hasher = Argon2Hasher(settings.argon2_time_cost, settings.argon2_memory_kib)
    accounts = Accounts(repo, hasher, clock)
    downloads = Downloads(store, renderer, ExifToolStripper(), root / "tmp")
    renditions = PrintRenditions(store, renderer, lambda view: editor.image_for(view, "preview"))
    printer = AlbumPrinter(renditions, lambda stamp: TypstPrintRenderer(timestamp=stamp))
    return Services(
        settings,
        repo,
        store,
        importer,
        worker,
        exiftool,
        accounts,
        editor,
        clock,
        downloads,
        trash,
        review,
        integrations,
        ml,
        ops,
        db,
        printer,
        stale_jobs,
        rechecks,
    )
