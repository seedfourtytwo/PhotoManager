"""People (FEATURES 2.8, 4.6): list, rename, hide, merge, split, a person's photos.

Every call takes ``visible``: the viewer, or the asset ids they may see. A person exists for them
only through faces on visible photos; anything else is "not found". People are shared by the
whole library, so edits are library-wide (the API lets only members and admins edit).
"""

from collections.abc import Sequence

from photo_assistant.domain.errors import InvalidError, NotFoundError
from photo_assistant.ports.ml import MlStore, PersonSummary, StoredFace, Visible

MAX_NAME = 100


class PersonNotFoundError(NotFoundError):
    pass


class FaceNotFoundError(NotFoundError):
    pass


class InvalidPeopleChangeError(InvalidError, ValueError):
    """A merge, a move of faces or a name that cannot be taken as asked."""


def _clean_name(name: str | None) -> str | None:
    cleaned = " ".join((name or "").split())
    if len(cleaned) > MAX_NAME:
        raise InvalidPeopleChangeError(f"name too long (max {MAX_NAME} characters)")
    return cleaned or None


class People:
    def __init__(self, store: MlStore) -> None:
        self._store = store

    def list_all(self, visible: Visible, *, hidden: bool | None = False) -> list[PersonSummary]:
        """The listed people; ``hidden=True`` the hidden ones instead, ``None`` both."""
        return self._store.list_persons(visible, hidden=hidden)

    def get(self, person_id: int, visible: Visible) -> PersonSummary:
        person = self._store.get_person(person_id, visible)
        if person is None:
            raise PersonNotFoundError(f"no person {person_id}")
        return person

    def rename(self, person_id: int, name: str | None, visible: Visible) -> PersonSummary:
        self.get(person_id, visible)
        self._store.rename_person(person_id, _clean_name(name))
        return self.get(person_id, visible)

    def set_hidden(self, person_id: int, hidden: bool, visible: Visible) -> PersonSummary:
        """Leave a person out of People, or list them again. Their faces stay theirs, so
        later photos of them join the same person, hidden or not."""
        self.get(person_id, visible)
        self._store.set_person_hidden(person_id, hidden)
        return self.get(person_id, visible)

    def merge(self, target_id: int, source_ids: Sequence[int], visible: Visible) -> PersonSummary:
        if target_id in source_ids:
            raise InvalidPeopleChangeError("cannot merge a person into itself")
        for person_id in (target_id, *source_ids):
            self.get(person_id, visible)
        self._store.merge_persons(target_id, source_ids)
        return self.get(target_id, visible)

    def split(
        self,
        face_ids: Sequence[int],
        visible: Visible,
        *,
        person_id: int | None = None,
        name: str | None = None,
    ) -> PersonSummary:
        """Move faces to ``person_id``, or to a new person called ``name``."""
        if not face_ids:
            raise InvalidPeopleChangeError("choose at least one face to move")
        faces = [self._store.get_face(face_id) for face_id in face_ids]
        shown = self._store.seen({face.asset_id for face in faces if face is not None}, visible)
        for face_id, face in zip(face_ids, faces, strict=True):
            if face is None or face.asset_id not in shown:
                raise FaceNotFoundError(f"no face {face_id}")
        if person_id is None:
            person_id = self._store.create_empty_person(_clean_name(name))
        else:
            self.get(person_id, visible)
        self._store.move_faces(face_ids, person_id)
        self._store.delete_empty_persons()
        return self.get(person_id, visible)

    def assets(self, person_id: int, visible: Visible) -> list[int]:
        self.get(person_id, visible)
        return self._store.person_asset_ids(person_id, visible)

    def faces_of_asset(self, asset_id: int, visible: Visible) -> list[StoredFace]:
        if not self._store.seen([asset_id], visible):
            raise LookupError(f"no asset {asset_id}")
        return self._store.faces_of_asset(asset_id)
