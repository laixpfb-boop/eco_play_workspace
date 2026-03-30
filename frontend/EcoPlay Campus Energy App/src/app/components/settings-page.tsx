import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { emitBuildingsUpdated } from '@/app/building-events';
import {
  type AlgorithmWeights,
  type BuildingSettings,
  type ComfortAnalysisResponse,
  createBuilding,
  deleteBuilding,
  exportOperatorCsv,
  getComfortAnalysis,
  getSettings,
  logoutOperator,
  updateAlgorithmWeights,
  updateBuildingSettings,
} from '@/api/ecoApi';

const emptyBuildingForm = {
  name: '',
  description: '',
  default_too_cold: 0,
  default_comfort: 0,
  default_too_warm: 0,
  default_temperature: 24,
  default_humidity: 50,
  default_co2: 650,
  default_noise: 45,
  default_light: 450,
};

function normalizeBuildingForm(building?: Partial<BuildingSettings> | null) {
  return {
    name: building?.name ?? '',
    description: building?.description ?? '',
    default_too_cold: building?.default_too_cold ?? 0,
    default_comfort: building?.default_comfort ?? 0,
    default_too_warm: building?.default_too_warm ?? 0,
    default_temperature: building?.default_temperature ?? 24,
    default_humidity: building?.default_humidity ?? 50,
    default_co2: building?.default_co2 ?? 650,
    default_noise: building?.default_noise ?? 45,
    default_light: building?.default_light ?? 450,
  };
}

export function SettingsPage() {
  const navigate = useNavigate();
  const [buildings, setBuildings] = useState<BuildingSettings[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [buildingForm, setBuildingForm] = useState(emptyBuildingForm);
  const [newBuildingForm, setNewBuildingForm] = useState(emptyBuildingForm);
  const [weights, setWeights] = useState<AlgorithmWeights>({
    too_cold: -0.5,
    comfort: 1,
    too_warm: -0.3,
    temp_factor: 0.1,
  });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [analysis, setAnalysis] = useState<ComfortAnalysisResponse | null>(null);

  const selectedBuilding = buildings.find((building) => building.id === selectedBuildingId) ?? null;

  async function loadSettings() {
    try {
      setError('');
      const [settings, analysisResponse] = await Promise.all([
        getSettings(),
        getComfortAnalysis(),
      ]);
      setBuildings(settings.buildings);
      setWeights(settings.algorithmWeights);
      setAnalysis(analysisResponse);
      if (settings.buildings.length > 0) {
        const nextSelectedId =
          selectedBuildingId && settings.buildings.some((building) => building.id === selectedBuildingId)
            ? selectedBuildingId
            : settings.buildings[0].id;
        setSelectedBuildingId(nextSelectedId);
        const selected = settings.buildings.find((building) => building.id === nextSelectedId) ?? settings.buildings[0];
        setBuildingForm(normalizeBuildingForm(selected));
      } else {
        setSelectedBuildingId(null);
        setBuildingForm(emptyBuildingForm);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load settings');
    }
  }

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (!selectedBuilding) {
      return;
    }
    setBuildingForm(normalizeBuildingForm(selectedBuilding));
  }, [selectedBuilding]);

  async function handleCreateBuilding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setError('');
      setMessage('');
      await createBuilding({ ...newBuildingForm, apply_today: true });
      setMessage('Building created and default data applied for today.');
      setNewBuildingForm(emptyBuildingForm);
      const latestSettings = await getSettings();
      setBuildings(latestSettings.buildings);
      setWeights(latestSettings.algorithmWeights);
      const createdBuilding = latestSettings.buildings[latestSettings.buildings.length - 1] ?? null;
      if (createdBuilding) {
        setSelectedBuildingId(createdBuilding.id);
      }
      emitBuildingsUpdated();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to create building');
    }
  }

  async function handleUpdateBuilding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedBuildingId) {
      return;
    }
    try {
      setError('');
      setMessage('');
      const payload = { ...normalizeBuildingForm(buildingForm), apply_today: true };
      await updateBuildingSettings(selectedBuildingId, payload);
      const latestSettings = await getSettings();
      const savedBuilding = latestSettings.buildings.find((building) => building.id === selectedBuildingId);
      if (!savedBuilding) {
        throw new Error(`Building id ${selectedBuildingId} was not found after saving.`);
      }
      const normalizedSaved = normalizeBuildingForm(savedBuilding);
      const fieldsToVerify: Array<keyof typeof emptyBuildingForm> = [
        'name',
        'description',
        'default_too_cold',
        'default_comfort',
        'default_too_warm',
        'default_temperature',
        'default_humidity',
        'default_co2',
        'default_noise',
        'default_light',
      ];
      const mismatchedField = fieldsToVerify.find((field) => normalizedSaved[field] !== payload[field]);
      if (mismatchedField) {
        throw new Error(`Saved settings did not persist correctly for field "${mismatchedField}".`);
      }
      setMessage('Building settings saved and today’s data updated.');
      setBuildings(latestSettings.buildings);
      setWeights(latestSettings.algorithmWeights);
      setBuildingForm(normalizedSaved);
      emitBuildingsUpdated();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to update building settings');
    }
  }

  async function handleUpdateWeights(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setError('');
      setMessage('');
      await updateAlgorithmWeights(weights);
      setMessage('Algorithm weights updated.');
      await loadSettings();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to update algorithm weights');
    }
  }

  async function handleDeleteBuilding(buildingToDelete: BuildingSettings) {
    if (!buildingToDelete) {
      return;
    }

    const confirmed = window.confirm(
      `Delete ${buildingToDelete.name}? This will remove its votes, sensor records, and saved settings.`
    );
    if (!confirmed) {
      return;
    }

    try {
      setError('');
      setMessage('');
      const deleteResult = await deleteBuilding(buildingToDelete.id);
      const deletedBuildingId = buildingToDelete.id;
      const latestSettings = await getSettings();
      const stillExists = latestSettings.buildings.some((building) => building.id === deleteResult.deleted_building_id);
      if (stillExists) {
        throw new Error(`Backend did not remove building id ${deleteResult.deleted_building_id} from the database.`);
      }

      setBuildings(latestSettings.buildings);
      setWeights(latestSettings.algorithmWeights);
      if (selectedBuildingId === deletedBuildingId) {
        setSelectedBuildingId(latestSettings.buildings[0]?.id ?? null);
      }
      if (latestSettings.buildings.length === 0) {
        setBuildingForm(emptyBuildingForm);
      }
      setMessage('Building deleted successfully.');
      emitBuildingsUpdated();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Failed to delete building');
    }
  }

  async function handleExportCsv() {
    try {
      setError('');
      const blob = await exportOperatorCsv();
      const downloadUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `ecoplay-export-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
      setMessage('CSV export downloaded.');
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Failed to export CSV');
    }
  }

  async function handleLogout() {
    try {
      await logoutOperator();
    } finally {
      navigate('/login', { replace: true });
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="px-4 py-4 sm:px-6 sm:py-5 space-y-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-600 mt-1">Add buildings, set default data, and tune weighted comfort parameters.</p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              onClick={handleExportCsv}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white"
            >
              Export CSV
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700"
            >
              Log Out
            </button>
          </div>
        </div>

        {message ? <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">{message}</div> : null}
        {error ? <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
          <form onSubmit={handleCreateBuilding} className="rounded-2xl bg-white p-5 shadow-sm border border-gray-200 space-y-3">
            <h2 className="text-lg font-semibold text-gray-900">Add Building</h2>
            <input
              value={newBuildingForm.name}
              onChange={(event) => setNewBuildingForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Building name"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={newBuildingForm.description}
              onChange={(event) => setNewBuildingForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Description"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <NumberInput label="Too Cold" value={newBuildingForm.default_too_cold} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_too_cold: value }))} />
              <NumberInput label="Comfort" value={newBuildingForm.default_comfort} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_comfort: value }))} />
              <NumberInput label="Too Warm" value={newBuildingForm.default_too_warm} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_too_warm: value }))} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <DecimalInput label="Temp" value={newBuildingForm.default_temperature} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_temperature: value }))} />
              <DecimalInput label="Humidity" value={newBuildingForm.default_humidity} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_humidity: value }))} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <DecimalInput label="CO2 (ppm)" value={newBuildingForm.default_co2} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_co2: value }))} />
              <DecimalInput label="Noise (dB)" value={newBuildingForm.default_noise} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_noise: value }))} />
              <DecimalInput label="Light (lux)" value={newBuildingForm.default_light} onChange={(value) => setNewBuildingForm((current) => ({ ...current, default_light: value }))} />
            </div>
            <button type="submit" className="w-full rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white">
              Add Building
            </button>
          </form>

          <form onSubmit={handleUpdateWeights} className="rounded-2xl bg-white p-5 shadow-sm border border-gray-200 space-y-3">
            <h2 className="text-lg font-semibold text-gray-900">Algorithm Weights</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <DecimalInput label="Too Cold Weight" value={weights.too_cold} onChange={(value) => setWeights((current) => ({ ...current, too_cold: value }))} />
              <DecimalInput label="Comfort Weight" value={weights.comfort} onChange={(value) => setWeights((current) => ({ ...current, comfort: value }))} />
              <DecimalInput label="Too Warm Weight" value={weights.too_warm} onChange={(value) => setWeights((current) => ({ ...current, too_warm: value }))} />
              <DecimalInput label="Temp Factor" value={weights.temp_factor} onChange={(value) => setWeights((current) => ({ ...current, temp_factor: value }))} />
            </div>
            <button type="submit" className="w-full rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white">
              Save Weights
            </button>
          </form>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] gap-5">
          <div className="rounded-2xl bg-white p-4 shadow-sm border border-gray-200 space-y-3 self-start">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Buildings</h2>
              <span className="text-xs text-gray-500">{buildings.length} total</span>
            </div>
            {buildings.length > 0 ? (
              <>
                <label className="block text-sm text-gray-700">
                  <span className="mb-1 block">Select building</span>
                  <select
                    value={selectedBuildingId ?? ''}
                    onChange={(event) => setSelectedBuildingId(Number(event.target.value))}
                    className="w-full rounded-xl border border-gray-300 px-3 py-3 text-sm font-semibold text-gray-900"
                  >
                    {buildings.map((building) => (
                      <option key={building.id} value={building.id}>
                        {building.name}
                      </option>
                    ))}
                  </select>
                </label>

                {selectedBuilding ? (
                  <div className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 space-y-3">
                    <div>
                      <div className="font-semibold text-gray-900">{selectedBuilding.name}</div>
                      <div className="mt-1 text-xs text-gray-500">{selectedBuilding.description || 'No description'}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteBuilding(selectedBuilding)}
                      className="w-full rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-50"
                    >
                      Delete Selected Building
                    </button>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-gray-600">No buildings available.</p>
            )}
          </div>

          <form onSubmit={handleUpdateBuilding} className="rounded-2xl bg-white p-5 shadow-sm border border-gray-200 space-y-3">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Building Defaults</h2>
              {selectedBuilding ? <span className="text-sm text-gray-500">Editing: {selectedBuilding.name}</span> : null}
            </div>

            {selectedBuilding ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <input
                    value={buildingForm.name}
                    onChange={(event) => setBuildingForm((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Building name"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                  <input
                    value={buildingForm.description}
                    onChange={(event) => setBuildingForm((current) => ({ ...current, description: event.target.value }))}
                    placeholder="Description"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <NumberInput label="Too Cold" value={buildingForm.default_too_cold} onChange={(value) => setBuildingForm((current) => ({ ...current, default_too_cold: value }))} />
                  <NumberInput label="Comfort" value={buildingForm.default_comfort} onChange={(value) => setBuildingForm((current) => ({ ...current, default_comfort: value }))} />
                  <NumberInput label="Too Warm" value={buildingForm.default_too_warm} onChange={(value) => setBuildingForm((current) => ({ ...current, default_too_warm: value }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <DecimalInput label="Default Temp" value={buildingForm.default_temperature} onChange={(value) => setBuildingForm((current) => ({ ...current, default_temperature: value }))} />
                  <DecimalInput label="Default Humidity" value={buildingForm.default_humidity} onChange={(value) => setBuildingForm((current) => ({ ...current, default_humidity: value }))} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <DecimalInput label="Default CO2 (ppm)" value={buildingForm.default_co2} onChange={(value) => setBuildingForm((current) => ({ ...current, default_co2: value }))} />
                  <DecimalInput label="Default Noise (dB)" value={buildingForm.default_noise} onChange={(value) => setBuildingForm((current) => ({ ...current, default_noise: value }))} />
                  <DecimalInput label="Default Light (lux)" value={buildingForm.default_light} onChange={(value) => setBuildingForm((current) => ({ ...current, default_light: value }))} />
                </div>
                <button type="submit" className="w-full rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white">
                  Save Building Defaults
                </button>
              </>
            ) : (
              <p className="text-sm text-gray-600">Create a building first to edit its defaults.</p>
            )}
          </form>
        </div>

        <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-200 space-y-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold text-gray-900">Comfort Analysis</h2>
            <p className="text-sm text-gray-600">
              Correlation analysis between comfort votes and sensor readings, with recommended operating targets.
            </p>
          </div>

          {analysis ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                <AnalysisCard
                  title="Samples"
                  value={String(analysis.sampleSize)}
                  hint="Daily vote/sensor rows joined"
                />
                <AnalysisCard
                  title="Temp Correlation"
                  value={formatNullableNumber(analysis.correlations.temperature_to_comfort)}
                  hint="Comfort vs temperature"
                />
                <AnalysisCard
                  title="Humidity Correlation"
                  value={formatNullableNumber(analysis.correlations.humidity_to_comfort)}
                  hint="Comfort vs humidity"
                />
                <AnalysisCard
                  title="Recommended Temp"
                  value={formatRecommendedRange(analysis.recommendation.temperature, analysis.recommendation.temperature_range, '°C')}
                  hint="Weighted by comfort votes"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-2">
                  <h3 className="text-sm font-semibold text-gray-900">Recommended Targets</h3>
                  <p className="text-sm text-gray-700">
                    Temperature: {formatRecommendedRange(analysis.recommendation.temperature, analysis.recommendation.temperature_range, '°C')}
                  </p>
                  <p className="text-sm text-gray-700">
                    Humidity: {formatRecommendedRange(analysis.recommendation.humidity, analysis.recommendation.humidity_range, '%')}
                  </p>
                  <p className="text-sm text-gray-700">
                    CO2 / Noise / Light defaults:
                    {' '}
                    {analysis.recommendation.reference_defaults
                      ? `${analysis.recommendation.reference_defaults.co2} ppm, ${analysis.recommendation.reference_defaults.noise} dB, ${analysis.recommendation.reference_defaults.light} lux`
                      : '--'}
                  </p>
                </div>

                <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-2">
                  <h3 className="text-sm font-semibold text-gray-900">Best Comfort Snapshots</h3>
                  <div className="space-y-2">
                    {analysis.buildingRecommendations.slice(0, 5).map((item) => (
                      <div key={item.building_id} className="rounded-lg bg-white border border-gray-200 px-3 py-2">
                        <div className="font-semibold text-gray-900">{item.building_name}</div>
                        <div className="text-xs text-gray-500">
                          {item.best_vote_date} · Comfort {item.comfort_percent}%
                        </div>
                        <div className="mt-1 text-sm text-gray-700">
                          Temp {item.temperature ?? '--'}°C · Humidity {item.humidity ?? '--'}%
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-600">Loading comfort analysis...</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AnalysisCard({ title, value, hint }: { title: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{title}</div>
      <div className="mt-2 text-2xl font-bold text-gray-900">{value}</div>
      <div className="mt-1 text-xs text-gray-500">{hint}</div>
    </div>
  );
}

function formatNullableNumber(value: number | null) {
  return value === null ? '--' : value.toFixed(2);
}

function formatRecommendedRange(
  center: number | null,
  range: { min: number; max: number } | null,
  unit: string
) {
  if (center === null || !range) {
    return '--';
  }
  return `${center}${unit} (${range.min}-${range.max}${unit})`;
}

function NumberInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="text-sm text-gray-700">
      <span className="mb-1 block">{label}</span>
      <input
        type="number"
        min="0"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
    </label>
  );
}

function DecimalInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="text-sm text-gray-700">
      <span className="mb-1 block">{label}</span>
      <input
        type="number"
        step="0.1"
        min="0"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
      />
    </label>
  );
}
