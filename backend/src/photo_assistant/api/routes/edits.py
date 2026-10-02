"""One edit recipe per photo, shared by everyone who may edit it (contract: Assets)."""

from fastapi import APIRouter, Response, status

from photo_assistant.api.deps import LOGGED_IN, ServicesDep, ViewerDep, require_view
from photo_assistant.api.schemas import RecipeIO
from photo_assistant.domain.access import Level
from photo_assistant.domain.edit_recipe import Recipe

router = APIRouter(prefix="/api/assets", tags=["edits"], dependencies=LOGGED_IN)


@router.get("/{asset_id}/edit")
def get_recipe(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> RecipeIO:
    require_view(services, viewer, asset_id)
    return RecipeIO.of(services.editor.recipe_of(asset_id))


@router.put("/{asset_id}/edit")
def put_recipe(services: ServicesDep, viewer: ViewerDep, asset_id: int, body: RecipeIO) -> RecipeIO:
    require_view(services, viewer, asset_id, Level.EDIT)
    recipe = Recipe.from_dict(body.model_dump())  # InvalidRecipeError: 422
    saved = services.editor.save(asset_id, recipe, viewer.user_id, services.clock.now())
    return RecipeIO.of(saved)


@router.delete("/{asset_id}/edit", status_code=status.HTTP_204_NO_CONTENT)
def revert(services: ServicesDep, viewer: ViewerDep, asset_id: int) -> Response:
    require_view(services, viewer, asset_id, Level.EDIT)
    services.editor.revert(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
