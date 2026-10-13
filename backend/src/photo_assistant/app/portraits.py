"""A person's portrait (FEATURES 2.8, issue 53): choose it, go back to the automatic one, and
make the round picture the browser shows.

The picture is a square cut from the library original (never from an edit: face boxes and
circles are fractions of the photo as it was found), at most ``PORTRAIT_EDGE`` px, cached
under ``derived/portrait/`` by content hash and cut. It is made on first request, once.
"""

import hashlib
from pathlib import Path
from typing import Protocol

from photo_assistant.app.people import FaceNotFoundError, People
from photo_assistant.domain.edit_recipe import Crop, Recipe
from photo_assistant.domain.errors import NotFoundError
from photo_assistant.domain.faces import Circle, fit_circle
from photo_assistant.domain.library_paths import portrait_relpath
from photo_assistant.ports import ImageRenderer, RenderSpec
from photo_assistant.ports.ml import MlStore, PersonSummary, Portrait, Visible

PORTRAIT_EDGE = 320  # px: twice the largest circle the pages show, for dense screens


class PortraitUnavailableError(NotFoundError):
    """The photo a portrait is cut from is not in the library folder."""


class LibraryFiles(Protocol):
    def absolute(self, relative_path: str) -> Path: ...


def portrait_recipe(portrait: Portrait) -> Recipe:
    """The cut as the renderer takes it; its key names the picture."""
    box = portrait.crop
    return Recipe(crop=Crop(box.x, box.y, box.width, box.height))


def portrait_version(portrait: Portrait) -> str:
    """Different for every photo and every cut: the picture at an address that carries it
    never changes, so a browser may keep it for good."""
    named = f"{portrait.content_hash}-{portrait_recipe(portrait).key}"
    return hashlib.sha256(named.encode()).hexdigest()[:16]


class Portraits:
    def __init__(
        self, store: MlStore, people: People, library: LibraryFiles, renderer: ImageRenderer
    ) -> None:
        self._store = store
        self._people = people
        self._library = library
        self._renderer = renderer

    def choose(
        self, person_id: int, face_id: int, circle: Circle, visible: Visible
    ) -> PersonSummary:
        """``circle`` on the photo of ``face_id`` is the person's portrait, for everyone who
        may see that photo. The face must be theirs, on a photo the viewer may see."""
        before = self._people.get(person_id, visible)
        face = self._store.face_portrait(face_id)
        if (
            face is None
            or face.face.person_id != person_id
            or not self._store.seen([face.face.asset_id], visible)
        ):
            raise FaceNotFoundError(f"no face {face_id}")
        self._store.set_portrait(person_id, face_id, fit_circle(circle, *face.photo_size))
        self._forget_chosen(before)
        return self._people.get(person_id, visible)

    def use_automatic(self, person_id: int, visible: Visible) -> PersonSummary:
        before = self._people.get(person_id, visible)
        self._store.clear_portrait(person_id)
        self._forget_chosen(before)
        return self._people.get(person_id, visible)

    def candidates(self, person_id: int, visible: Visible, limit: int) -> list[Portrait]:
        """The faces to choose from, the best first."""
        self._people.get(person_id, visible)
        return self._store.person_faces(person_id, visible, limit)

    def of_person(self, person_id: int, visible: Visible) -> Portrait:
        portrait = self._people.get(person_id, visible).portrait
        if portrait is None:  # a person is found through a face, so this is a race at most
            raise PortraitUnavailableError(f"person {person_id} has no portrait")
        return portrait

    def of_face(self, face_id: int, visible: Visible) -> Portrait:
        portrait = self._store.face_portrait(face_id)
        if portrait is None or not self._store.seen([portrait.face.asset_id], visible):
            raise FaceNotFoundError(f"no face {face_id}")
        return portrait

    def image(self, portrait: Portrait) -> Path:
        """The WebP to show, cut from the original on first use."""
        path = self._path(portrait)
        if not path.is_file():
            original = self._library.absolute(portrait.library_path)
            if not original.is_file():
                raise PortraitUnavailableError("the original of this photo is missing")
            spec = RenderSpec(recipe=portrait_recipe(portrait), max_edge=PORTRAIT_EDGE)
            self._renderer.render_variant(original, path, spec)
        return path

    def _path(self, portrait: Portrait) -> Path:
        relative = portrait_relpath(portrait.content_hash, portrait_recipe(portrait).key)
        return self._library.absolute(str(relative))

    def _forget_chosen(self, person: PersonSummary) -> None:
        """Delete the picture of a cut nobody has any more (a derived file only). Automatic
        pictures stay: they are what the faces to choose from show."""
        if person.portrait is not None and person.portrait.chosen:
            self._path(person.portrait).unlink(missing_ok=True)
