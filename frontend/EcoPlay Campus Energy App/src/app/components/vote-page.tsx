import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { Thermometer, Droplets, Wind } from 'lucide-react';
import HKUSTLogo from '../../imports/Hong_Kong_University_of_Science_and_Technology_symbol.svg';
import { BUILDINGS_UPDATED_EVENT } from '@/app/building-events';
import { getBuildingFromParam } from '@/app/url-context';
import {
  type Building,
  type BuildingVotes,
  type SensorReading,
  getBuildings,
  getSensorData,
  getVotes,
  updateVotes,
} from '@/api/ecoApi';

const emptyVotes: BuildingVotes = {
  building_id: 0,
  too_cold: 0,
  comfort: 0,
  too_warm: 0,
  total: 0,
  too_cold_percent: 0,
  comfort_percent: 0,
  too_warm_percent: 0,
};

const fallbackSensor: SensorReading = {
  building_id: 0,
  temperature: 0,
  humidity: 0,
  read_time: '',
};

function buildEmptyVotes(buildingId: number): BuildingVotes {
  return {
    ...emptyVotes,
    building_id: buildingId,
  };
}

export function VotePage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [votes, setVotes] = useState<BuildingVotes>(emptyVotes);
  const [sensor, setSensor] = useState<SensorReading>(fallbackSensor);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const selectedBuilding = buildings.find((building) => building.id === selectedBuildingId) ?? null;
  const buildingParam = searchParams.get('building');
  const isPublicView = location.pathname.startsWith('/user');

  async function loadBuildings(preferredBuildingId?: number | null) {
    try {
      setIsLoading(true);
      const buildingList = await getBuildings();

      setBuildings(buildingList);
      if (buildingList.length === 0) {
        setSelectedBuildingId(null);
        return;
      }

      const buildingFromUrl = getBuildingFromParam(buildingList, buildingParam);

      const nextSelectedId =
        buildingFromUrl?.id ??
        (preferredBuildingId && buildingList.some((building) => building.id === preferredBuildingId)
          ? preferredBuildingId
          : selectedBuildingId && buildingList.some((building) => building.id === selectedBuildingId)
          ? selectedBuildingId
          : buildingList[0].id);
      setSelectedBuildingId(nextSelectedId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load buildings');
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function loadInitialBuildings() {
      await loadBuildings();
    }

    loadInitialBuildings();
    return () => {
      cancelled = true;
    };
  }, [buildingParam]);

  useEffect(() => {
    function handleBuildingsUpdated() {
      loadBuildings(selectedBuildingId);
    }

    window.addEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    return () => {
      window.removeEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    };
  }, [selectedBuildingId, buildings, buildingParam]);

  useEffect(() => {
    if (!selectedBuilding) {
      return;
    }

    let cancelled = false;

    async function loadBuildingData() {
      try {
        setIsLoading(true);
        setError('');
        setVotes(buildEmptyVotes(selectedBuilding.id));
        setSensor({ ...fallbackSensor, building_id: selectedBuilding.id });
        const [voteData, sensorData] = await Promise.all([
          getVotes(selectedBuilding.name),
          getSensorData(selectedBuilding.id),
        ]);
        if (cancelled) {
          return;
        }

        setVotes(voteData);
        setSensor(sensorData);
      } catch (loadError) {
        if (!cancelled) {
          setVotes(buildEmptyVotes(selectedBuilding.id));
          setSensor({ ...fallbackSensor, building_id: selectedBuilding.id });
          setError(loadError instanceof Error ? loadError.message : 'Failed to load building data');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    loadBuildingData();
    return () => {
      cancelled = true;
    };
  }, [selectedBuilding]);

  const handleVote = async (type: 'too_cold' | 'comfort' | 'too_warm') => {
    if (!selectedBuilding || isSubmitting) {
      return;
    }

    const nextVotes: BuildingVotes = {
      ...votes,
      [type]: votes[type] + 1,
      total: votes.total + 1,
    };
    nextVotes.too_cold_percent = nextVotes.total === 0 ? 0 : Number(((nextVotes.too_cold / nextVotes.total) * 100).toFixed(1));
    nextVotes.comfort_percent = nextVotes.total === 0 ? 0 : Number(((nextVotes.comfort / nextVotes.total) * 100).toFixed(1));
    nextVotes.too_warm_percent = nextVotes.total === 0 ? 0 : Number(((nextVotes.too_warm / nextVotes.total) * 100).toFixed(1));

    const previousVotes = votes;
    setVotes(nextVotes);
    setIsSubmitting(true);
    setError('');

    try {
      await updateVotes(selectedBuilding.id, {
        too_cold: nextVotes.too_cold,
        comfort: nextVotes.comfort,
        too_warm: nextVotes.too_warm,
        total: nextVotes.total,
      });
    } catch (submitError) {
      setVotes(previousVotes);
      setError(submitError instanceof Error ? submitError.message : 'Failed to submit vote');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-white">
      <div className={`flex ${isPublicView ? 'flex-col' : 'items-center justify-center'} bg-white border-b border-gray-200 gap-2 px-4 py-4 sm:gap-3 ${isPublicView ? '' : 'sm:py-4'}`}>
        <img src={HKUSTLogo} alt="HKUST Logo" className="h-10 sm:h-12 mx-auto" />
        <div className="text-center text-base leading-tight sm:text-lg text-gray-700">
          Student Sustainable Smart Campus Living Lab
        </div>
      </div>

      <div className={`bg-blue-100 text-center px-4 py-4 sm:px-6 ${isPublicView ? '' : 'sm:py-5'}`}>
        <h1 className={`${isPublicView ? 'text-3xl' : 'text-2xl sm:text-3xl'} leading-tight font-semibold text-gray-800`}>
          HKUST EcoPlay - Student Environmental Feedback
        </h1>
        <div className="mt-3 space-y-2 sm:flex sm:items-center sm:justify-center sm:gap-3 sm:space-y-0">
          <label htmlFor="building-select" className="text-sm text-gray-700">
            Building
          </label>
          <select
            id="building-select"
            value={selectedBuildingId ?? ''}
            onChange={(event) => setSelectedBuildingId(Number(event.target.value))}
            className={`rounded-md border border-blue-200 bg-white text-gray-800 w-full sm:w-auto ${isPublicView ? 'px-4 py-3 text-base' : 'px-3 py-2 text-sm sm:text-base'}`}
          >
            {buildings.map((building) => (
              <option key={building.id} value={building.id}>
                {building.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={`bg-gray-50 grid ${isPublicView ? 'grid-cols-3' : 'grid-cols-1 md:grid-cols-3'} gap-3 sm:gap-4 px-4 sm:px-6 lg:px-8 py-4 sm:py-5`}>
        <div className="flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 py-4 sm:py-3">
          <Thermometer className="w-7 h-7 sm:w-8 sm:h-8 text-blue-500" />
          <span className={`${isPublicView ? 'text-xl sm:text-2xl' : 'text-2xl sm:text-3xl'} text-gray-800`}>
            {isLoading ? '--' : `${sensor.temperature.toFixed(1)}°C`}
          </span>
        </div>
        <div className="flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 py-4 sm:py-3">
          <Droplets className="w-7 h-7 sm:w-8 sm:h-8 text-blue-500" />
          <span className={`${isPublicView ? 'text-xl sm:text-2xl' : 'text-2xl sm:text-3xl'} text-gray-800`}>
            {isLoading ? '--' : `${sensor.humidity.toFixed(1)}%`}
          </span>
        </div>
        <div className="flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 py-4 sm:py-3">
          <Wind className="w-7 h-7 sm:w-8 sm:h-8 text-green-600" />
          <span className={`${isPublicView ? 'text-lg sm:text-xl' : 'text-xl sm:text-2xl'} text-gray-800`}>
            {isPublicView ? '650 ppm' : selectedBuilding ? `ID ${selectedBuilding.id}` : '--'}
          </span>
        </div>
      </div>

      <div className={`flex-1 min-h-0 grid grid-cols-1 ${isPublicView ? '' : 'md:grid-cols-3'} gap-4 sm:gap-5 lg:gap-6 px-4 sm:px-6 lg:px-8 py-4 content-start ${isPublicView ? '' : 'md:items-stretch'}`}>
        <button
          onClick={() => handleVote('too_cold')}
          disabled={!selectedBuilding || isSubmitting}
          className={`flex flex-col items-center justify-center gap-3 bg-blue-400 hover:bg-blue-500 disabled:opacity-60 text-white rounded-2xl transition-colors ${isPublicView ? 'px-6 py-7 min-h-[160px]' : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className={`${isPublicView ? 'text-4xl' : 'text-4xl lg:text-5xl'}`}>❄️</div>
          <div className={`${isPublicView ? 'text-2xl' : 'text-2xl lg:text-3xl'} font-bold`}>Too Cold</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.too_cold_percent}%`}</div>
        </button>

        <button
          onClick={() => handleVote('comfort')}
          disabled={!selectedBuilding || isSubmitting}
          className={`flex flex-col items-center justify-center gap-3 bg-green-500 hover:bg-green-600 disabled:opacity-60 text-white rounded-2xl transition-colors ${isPublicView ? 'px-6 py-7 min-h-[160px]' : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className={`${isPublicView ? 'text-4xl' : 'text-4xl lg:text-5xl'}`}>☀️</div>
          <div className={`${isPublicView ? 'text-2xl' : 'text-2xl lg:text-3xl'} font-bold`}>Comfort</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.comfort_percent}%`}</div>
        </button>

        <button
          onClick={() => handleVote('too_warm')}
          disabled={!selectedBuilding || isSubmitting}
          className={`flex flex-col items-center justify-center gap-3 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white rounded-2xl transition-colors ${isPublicView ? 'px-6 py-7 min-h-[160px]' : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className={`${isPublicView ? 'text-4xl' : 'text-4xl lg:text-5xl'}`}>🔥</div>
          <div className={`${isPublicView ? 'text-2xl' : 'text-2xl lg:text-3xl'} font-bold`}>Too Warm</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.too_warm_percent}%`}</div>
        </button>
      </div>

      <div className={`text-center bg-white border-t border-gray-200 px-4 py-4 ${isPublicView ? '' : 'sm:px-6'}`}>
        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <p className={`${isPublicView ? 'text-sm leading-6' : 'text-sm sm:text-base leading-6 sm:leading-tight'} text-gray-700`}>
            {isPublicView ? 'Votes (Session):' : 'Votes Today:'}
            <span className="text-blue-600 font-semibold"> Too Cold: {votes.too_cold}</span>
            {' | '}
            <span className="text-green-600 font-semibold">Comfort: {votes.comfort}</span>
            {' | '}
            <span className="text-orange-600 font-semibold">Too Warm: {votes.too_warm}</span>
            {isPublicView ? null : (
              <>
                {' | '}
                <span className="text-gray-800 font-semibold">Total: {votes.total}</span>
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
