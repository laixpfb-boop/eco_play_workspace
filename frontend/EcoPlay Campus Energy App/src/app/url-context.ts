import { type Building } from '@/api/ecoApi';

export function normalizeBuildingValue(value: string) {
  return decodeURIComponent(value).trim().toLowerCase();
}

export function getBuildingFromParam(buildings: Building[], rawValue: string | null) {
  if (!rawValue) {
    return null;
  }

  const normalizedValue = normalizeBuildingValue(rawValue);
  const numericId = Number(rawValue);
  if (Number.isInteger(numericId)) {
    const byId = buildings.find((building) => building.id === numericId);
    if (byId) {
      return byId;
    }
  }

  return (
    buildings.find((building) => normalizeBuildingValue(building.name) === normalizedValue) ??
    null
  );
}
