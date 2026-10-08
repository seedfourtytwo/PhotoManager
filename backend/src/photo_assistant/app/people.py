"""People (FEATURES 2.8, 4.6): list, rename, merge, split, a person's photos.

Every call takes ``visible``: the asset ids the viewer may see. A person exists for a viewer
only through faces on visible photos; anything else is "not found". People are shared by the
whole library, so edits are library-wide (the API lets only members and admins edit).
"""

from collections.abc import Collection, Sequence

from photo_assistant.domain.errors import InvalidError, NotFoundError
from photo_assistant.ports.ml import MlStore, PersonSummary, StoredFace

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

    def list_all(self, visible: Collection[int]) -> list[PersonSummary]:
        return self._store.list_persons(visible)

    def get(self, person_id: int, visible: Collection[int]) -> PersonSummary:
        person = self._store.get_person(person_id, visible)
        if person is None:
            raise PersonNotFoundError(f"no person {person_id}")
        return person

    def rename(self, person_id: int, name: str | None, visible: Collection[int]) -> PersonSummary:
        self.get(person_id, visible)
        self._store.rename_person(person_id, _clean_name(name))
        return self.get(person_id, visible)

    def merge(
        self, target_id: int, source_ids: Sequence[int], visible: Collection[int]
    ) -> PersonSummary:
        if target_id in source_ids:
            raise InvalidPeopleChangeError("cannot merge a person into itself")
        for person_id in (target_id, *source_ids):
            self.get(person_id, visible)
        self._store.merge_persons(target_id, source_ids)
        return self.get(target_id, visible)

    def split(
        self,
        face_ids: Sequence[int],
        visible: Collection[int],
        *,
        person_id: int | None = None,
        name: str | None = None,
    ) -> PersonSummary:
        """Move faces to ``person_id``, or to a new person called ``name``."""
        if not face_ids:
            raise InvalidPeopleChangeError("choose at least one face to move")
        for face_id in face_ids:
            face = self._store.get_face(face_id)
            if face is None or face.asset_id not in visible:
                raise FaceNotFoundError(f"no face {face_id}")
        if person_id is None:
            person_id = self._store.create_empty_person(_clean_name(name))
        else:
            self.get(person_id, visible)
        self._store.move_faces(face_ids, person_id)
        self._store.delete_empty_persons()
        return self.get(person_id, visible)

    def assets(self, person_id: int, visible: Collection[int]) -> list[int]:
        self.get(person_id, visible)
        return self._store.person_asset_ids(person_id, visible)

    def faces_of_asset(self, asset_id: int, visible: Collection[int]) -> list[StoredFace]:
        if asset_id not in visible:
            raise LookupError(f"no asset {asset_id}")
        return self._store.faces_of_asset(asset_id)
