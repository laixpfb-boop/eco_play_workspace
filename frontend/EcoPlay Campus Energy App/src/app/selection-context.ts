const PUBLIC_BUILDING_KEY = 'ecoplay:selected-building:public';
const OPERATOR_BUILDING_KEY = 'ecoplay:selected-building:operator';

function getStorageKey(isPublicView: boolean) {
  return isPublicView ? PUBLIC_BUILDING_KEY : OPERATOR_BUILDING_KEY;
}

export function getSavedBuildingId(isPublicView: boolean): number | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const rawValue = window.localStorage.getItem(getStorageKey(isPublicView));
  if (!rawValue) {
    return null;
  }

  const numericValue = Number(rawValue);
  return Number.isFinite(numericValue) ? numericValue : null;
}

export function saveBuildingId(isPublicView: boolean, buildingId: number | null) {
  if (typeof window === 'undefined') {
    return;
  }

  const storageKey = getStorageKey(isPublicView);
  if (buildingId === null) {
    window.localStorage.removeItem(storageKey);
    return;
  }

  window.localStorage.setItem(storageKey, String(buildingId));
}
