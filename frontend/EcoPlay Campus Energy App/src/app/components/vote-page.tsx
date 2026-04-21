import { useEffect, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { Thermometer, Droplets, Wind } from 'lucide-react';
import HKUSTLogo from '../../imports/Hong_Kong_University_of_Science_and_Technology_symbol.svg';
import { BUILDINGS_UPDATED_EVENT } from '@/app/building-events';
import { getSavedBuildingId, saveBuildingId } from '@/app/selection-context';
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

type VoteType = 'too_cold' | 'comfort' | 'too_warm';

type VoteFeedbackEffect = {
  type: VoteType;
  emoji: string;
  message: string;
  panelClass: string;
};

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
  co2: 0,
  read_time: '',
};
const DEFAULT_BUILDING_NAME = 'Sustainability Office';

function buildEmptyVotes(buildingId: number): BuildingVotes {
  return {
    ...emptyVotes,
    building_id: buildingId,
  };
}

export function VotePage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [votes, setVotes] = useState<BuildingVotes>(emptyVotes);
  const [sensor, setSensor] = useState<SensorReading>(fallbackSensor);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittingVoteType, setSubmittingVoteType] = useState<VoteType | null>(null);
  const [pressedVoteType, setPressedVoteType] = useState<VoteType | null>(null);
  const [voteFeedbackEffect, setVoteFeedbackEffect] = useState<VoteFeedbackEffect | null>(null);
  const [error, setError] = useState('');
  const optimisticVotesRef = useRef<BuildingVotes | null>(null);

  const selectedBuilding = buildings.find((building) => building.id === selectedBuildingId) ?? null;
  const buildingParam = searchParams.get('building');
  const isPublicView = location.pathname.startsWith('/user');

  function updateBuildingSearchParam(building: Building | null) {
    const nextParams = new URLSearchParams(searchParams);
    if (building) {
      nextParams.set('building', building.name);
    } else {
      nextParams.delete('building');
    }
    setSearchParams(nextParams, { replace: true });
  }

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
      const savedBuildingId = getSavedBuildingId(isPublicView);
      const defaultBuildingId = buildingList.find((building) => building.name === DEFAULT_BUILDING_NAME)?.id;

      const nextSelectedId =
        buildingFromUrl?.id ??
        (savedBuildingId && buildingList.some((building) => building.id === savedBuildingId)
          ? savedBuildingId
          : preferredBuildingId && buildingList.some((building) => building.id === preferredBuildingId)
          ? preferredBuildingId
          : selectedBuildingId && buildingList.some((building) => building.id === selectedBuildingId)
          ? selectedBuildingId
          : defaultBuildingId
          ? defaultBuildingId
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
  }, [buildingParam, isPublicView]);

  useEffect(() => {
    function handleBuildingsUpdated() {
      loadBuildings(selectedBuildingId);
    }

    window.addEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    return () => {
      window.removeEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    };
  }, [selectedBuildingId, buildings, buildingParam, isPublicView]);

  useEffect(() => {
    saveBuildingId(isPublicView, selectedBuildingId);
  }, [isPublicView, selectedBuildingId]);

  useEffect(() => {
    if (!selectedBuilding) {
      return;
    }

    if (buildingParam === selectedBuilding.name) {
      return;
    }

    updateBuildingSearchParam(selectedBuilding);
  }, [selectedBuilding, buildingParam]);

  useEffect(() => {
    if (!selectedBuilding) {
      return;
    }

    let cancelled = false;

    async function loadBuildingData(showLoading = false) {
      try {
        if (showLoading) {
          setIsLoading(true);
          setVotes(buildEmptyVotes(selectedBuilding.id));
          setSensor({ ...fallbackSensor, building_id: selectedBuilding.id });
        }
        setError('');
        const [voteData, sensorData] = await Promise.all([
          getVotes(selectedBuilding.name),
          getSensorData(selectedBuilding.id),
        ]);
        if (cancelled) {
          return;
        }

        const optimisticVotes = optimisticVotesRef.current;
        if (optimisticVotes && voteData.total < optimisticVotes.total) {
          return;
        }
        if (optimisticVotes && voteData.total >= optimisticVotes.total) {
          optimisticVotesRef.current = null;
        }
        setVotes(voteData);
        setSensor(sensorData);
      } catch (loadError) {
        if (!cancelled) {
          if (showLoading) {
            setVotes(buildEmptyVotes(selectedBuilding.id));
            setSensor({ ...fallbackSensor, building_id: selectedBuilding.id });
          }
          setError(loadError instanceof Error ? loadError.message : 'Failed to load building data');
        }
      } finally {
        if (!cancelled && showLoading) {
          setIsLoading(false);
        }
      }
    }

    loadBuildingData(true);
    const intervalId = window.setInterval(() => {
      loadBuildingData(false);
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedBuilding]);

  const handleVote = async (type: VoteType) => {
    if (!selectedBuilding || isSubmitting) {
      return;
    }

    // Keep a brief visual feedback even if submit returns quickly.
    setPressedVoteType(type);
    window.setTimeout(() => {
      setPressedVoteType((previousType) => (previousType === type ? null : previousType));
    }, 700);
    const effectByType: Record<VoteType, VoteFeedbackEffect> = {
      too_cold: {
        type: 'too_cold',
        emoji: '🥶',
        message: 'Thanks for your feedback',
        panelClass: 'from-blue-200/95 to-blue-400/90 text-blue-900',
      },
      comfort: {
        type: 'comfort',
        emoji: '😌',
        message: 'Thanks for your feedback',
        panelClass: 'from-green-200/95 to-green-400/90 text-green-900',
      },
      too_warm: {
        type: 'too_warm',
        emoji: '🥵',
        message: 'Thanks for your feedback',
        panelClass: 'from-orange-200/95 to-orange-400/90 text-orange-900',
      },
    };
    setVoteFeedbackEffect(effectByType[type]);
    window.setTimeout(() => {
      setVoteFeedbackEffect((previousEffect) => (previousEffect?.type === type ? null : previousEffect));
    }, 1000);

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
    optimisticVotesRef.current = nextVotes;
    setIsSubmitting(true);
    setSubmittingVoteType(type);
    setError('');

    try {
      await updateVotes(selectedBuilding.id, {
        too_cold: nextVotes.too_cold,
        comfort: nextVotes.comfort,
        too_warm: nextVotes.too_warm,
        total: nextVotes.total,
      });
      // Ensure UI stays at least on the just-submitted count.
      setVotes(nextVotes);
    } catch (submitError) {
      setVotes(previousVotes);
      optimisticVotesRef.current = null;
      setError(submitError instanceof Error ? submitError.message : 'Failed to submit vote');
    } finally {
      setIsSubmitting(false);
      setSubmittingVoteType(null);
    }
  };

  const publicVoteCardClass = 'px-4 py-4 min-h-[112px]';
  const publicVoteLabelClass = 'text-3xl sm:text-4xl';
  const publicVoteIconClass = 'text-3xl';

  return (
    <div className="flex flex-col h-full min-h-0 bg-white">
      <style>
        {`
          @keyframes vote-feedback-pop {
            0% { opacity: 0; transform: scale(0.85) translateY(10px); }
            18% { opacity: 1; transform: scale(1.03) translateY(0); }
            72% { opacity: 1; transform: scale(1) translateY(0); }
            100% { opacity: 0; transform: scale(0.98) translateY(4px); }
          }
          @-webkit-keyframes vote-feedback-pop {
            0% { opacity: 0; -webkit-transform: scale(0.85) translateY(10px); }
            18% { opacity: 1; -webkit-transform: scale(1.03) translateY(0); }
            72% { opacity: 1; -webkit-transform: scale(1) translateY(0); }
            100% { opacity: 0; -webkit-transform: scale(0.98) translateY(4px); }
          }
          .vote-feedback-pop {
            animation: vote-feedback-pop 1.2s ease-out;
            -webkit-animation: vote-feedback-pop 1.2s ease-out;
            transform-origin: center;
            will-change: transform, opacity;
          }
          @keyframes vote-button-bump {
            0% { transform: scale(1); }
            35% { transform: scale(1.08); }
            100% { transform: scale(1); }
          }
          @-webkit-keyframes vote-button-bump {
            0% { -webkit-transform: scale(1); }
            35% { -webkit-transform: scale(1.08); }
            100% { -webkit-transform: scale(1); }
          }
          .vote-button-bump {
            animation: vote-button-bump 0.65s ease-out;
            -webkit-animation: vote-button-bump 0.65s ease-out;
            will-change: transform;
          }
        `}
      </style>
      {voteFeedbackEffect ? (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-black/25 px-4">
          <div className={`vote-feedback-pop rounded-3xl bg-gradient-to-b shadow-2xl px-8 py-6 text-center ${voteFeedbackEffect.panelClass}`}>
            <div className="text-7xl sm:text-8xl leading-none">{voteFeedbackEffect.emoji}</div>
            <p className="mt-4 text-2xl sm:text-3xl font-bold">{voteFeedbackEffect.message}</p>
          </div>
        </div>
      ) : null}
      <div className="flex-1 min-h-0 overflow-y-auto">
      <div className={`flex ${isPublicView ? 'flex-col' : 'items-center justify-center'} bg-white border-b border-gray-200 gap-2 px-4 ${isPublicView ? 'py-2' : 'py-4 sm:gap-3 sm:py-4'}`}>
        <img src={HKUSTLogo} alt="HKUST Logo" className={`${isPublicView ? 'h-8' : 'h-10 sm:h-12'} mx-auto`} />
        <div className={`text-center leading-tight text-gray-700 ${isPublicView ? 'text-sm' : 'text-base sm:text-lg'}`}>
          Student Sustainable Smart Campus Living Lab
        </div>
      </div>

      <div className={`bg-blue-100 text-center px-4 sm:px-6 ${isPublicView ? 'py-3' : 'py-4 sm:py-5'}`}>
        <h1 className={`${isPublicView ? 'text-2xl' : 'text-2xl sm:text-3xl'} leading-tight font-semibold text-gray-800`}>
          HKUST EcoPlay - Student Environmental Feedback
        </h1>
        <div className={`space-y-2 sm:flex sm:items-center sm:justify-center sm:gap-3 sm:space-y-0 ${isPublicView ? 'mt-2' : 'mt-3'}`}>
          <label htmlFor="building-select" className={`text-gray-700 ${isPublicView ? 'text-xs' : 'text-sm'}`}>
            Building
          </label>
          <select
            id="building-select"
            value={selectedBuildingId ?? ''}
            onChange={(event) => {
              const nextBuildingId = Number(event.target.value);
              const nextBuilding = buildings.find((building) => building.id === nextBuildingId) ?? null;
              setSelectedBuildingId(nextBuildingId);
              updateBuildingSearchParam(nextBuilding);
            }}
            className={`rounded-md border border-blue-200 bg-white text-gray-800 w-full sm:w-auto ${isPublicView ? 'px-4 py-2 text-sm' : 'px-3 py-2 text-sm sm:text-base'}`}
          >
            {buildings.map((building) => (
              <option key={building.id} value={building.id}>
                {building.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className={`bg-gray-50 grid ${isPublicView ? 'grid-cols-3' : 'grid-cols-1 md:grid-cols-3'} gap-3 sm:gap-4 px-4 sm:px-6 lg:px-8 ${isPublicView ? 'py-3' : 'py-4 sm:py-5'}`}>
        <div className={`flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 ${isPublicView ? 'py-3' : 'py-4 sm:py-3'}`}>
          <Thermometer className="w-7 h-7 sm:w-8 sm:h-8 text-blue-500" />
          <span className={`${isPublicView ? 'text-xl sm:text-2xl' : 'text-2xl sm:text-3xl'} text-gray-800`}>
            {isLoading ? '--' : `${sensor.temperature.toFixed(1)}°C`}
          </span>
        </div>
        <div className={`flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 ${isPublicView ? 'py-3' : 'py-4 sm:py-3'}`}>
          <Droplets className="w-7 h-7 sm:w-8 sm:h-8 text-blue-500" />
          <span className={`${isPublicView ? 'text-xl sm:text-2xl' : 'text-2xl sm:text-3xl'} text-gray-800`}>
            {isLoading ? '--' : `${sensor.humidity.toFixed(1)}%`}
          </span>
        </div>
        <div className={`flex items-center justify-center gap-2 bg-white rounded-lg border border-gray-200 ${isPublicView ? 'py-3' : 'py-4 sm:py-3'}`}>
          <Wind className="w-7 h-7 sm:w-8 sm:h-8 text-green-600" />
          <span className={`${isPublicView ? 'text-lg sm:text-xl' : 'text-xl sm:text-2xl'} text-gray-800`}>
            {isLoading ? '--' : `CO2 ${sensor.co2.toFixed(0)} ppm`}
          </span>
        </div>
      </div>

      <div className={`flex-1 min-h-0 grid grid-cols-1 ${isPublicView ? '' : 'md:grid-cols-3'} gap-4 sm:gap-5 lg:gap-6 px-4 sm:px-6 lg:px-8 py-4 content-start ${isPublicView ? '' : 'md:items-stretch'}`}>
        <button
          onClick={() => handleVote('too_cold')}
          disabled={!selectedBuilding || isSubmitting}
          className={`relative flex flex-col items-center justify-center ${isPublicView ? 'gap-2' : 'gap-3'} bg-blue-400 hover:bg-blue-500 active:scale-[0.98] active:brightness-95 text-white rounded-2xl shadow-md hover:shadow-lg transition-all duration-150 ${submittingVoteType === 'too_cold' || pressedVoteType === 'too_cold' ? 'ring-4 ring-blue-200/80 scale-[0.98] shadow-xl' : ''} ${pressedVoteType === 'too_cold' ? 'vote-button-bump' : ''} ${isPublicView ? publicVoteCardClass : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className="absolute right-3 top-3 rounded-full bg-white/25 px-3 py-1 text-base sm:text-lg font-bold tabular-nums">
            {votes.too_cold}
          </div>
          <div className={`${isPublicView ? publicVoteIconClass : 'text-4xl lg:text-5xl'}`}>❄️</div>
          <div className={`${isPublicView ? publicVoteLabelClass : 'text-4xl lg:text-5xl'} font-bold`}>Too Cold</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.too_cold_percent}%`}</div>
        </button>

        <button
          onClick={() => handleVote('comfort')}
          disabled={!selectedBuilding || isSubmitting}
          className={`relative flex flex-col items-center justify-center ${isPublicView ? 'gap-2' : 'gap-3'} bg-green-500 hover:bg-green-600 active:scale-[0.98] active:brightness-95 text-white rounded-2xl shadow-md hover:shadow-lg transition-all duration-150 ${submittingVoteType === 'comfort' || pressedVoteType === 'comfort' ? 'ring-4 ring-green-200/80 scale-[0.98] shadow-xl' : ''} ${pressedVoteType === 'comfort' ? 'vote-button-bump' : ''} ${isPublicView ? publicVoteCardClass : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className="absolute right-3 top-3 rounded-full bg-white/25 px-3 py-1 text-base sm:text-lg font-bold tabular-nums">
            {votes.comfort}
          </div>
          <div className={`${isPublicView ? publicVoteIconClass : 'text-4xl lg:text-5xl'}`}>☀️</div>
          <div className={`${isPublicView ? publicVoteLabelClass : 'text-4xl lg:text-5xl'} font-bold`}>Comfort</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.comfort_percent}%`}</div>
        </button>

        <button
          onClick={() => handleVote('too_warm')}
          disabled={!selectedBuilding || isSubmitting}
          className={`relative flex flex-col items-center justify-center ${isPublicView ? 'gap-2' : 'gap-3'} bg-orange-500 hover:bg-orange-600 active:scale-[0.98] active:brightness-95 text-white rounded-2xl shadow-md hover:shadow-lg transition-all duration-150 ${submittingVoteType === 'too_warm' || pressedVoteType === 'too_warm' ? 'ring-4 ring-orange-200/80 scale-[0.98] shadow-xl' : ''} ${pressedVoteType === 'too_warm' ? 'vote-button-bump' : ''} ${isPublicView ? publicVoteCardClass : 'px-6 py-7 min-h-[170px] md:min-h-[220px]'}`}
        >
          <div className="absolute right-3 top-3 rounded-full bg-white/25 px-3 py-1 text-base sm:text-lg font-bold tabular-nums">
            {votes.too_warm}
          </div>
          <div className={`${isPublicView ? publicVoteIconClass : 'text-4xl lg:text-5xl'}`}>🔥</div>
          <div className={`${isPublicView ? publicVoteLabelClass : 'text-4xl lg:text-5xl'} font-bold`}>Too Warm</div>
          <div className="text-sm">{isPublicView ? '' : `${votes.too_warm_percent}%`}</div>
        </button>
      </div>

      <div className={`text-center bg-white border-t border-gray-200 px-4 py-4 ${isPublicView ? '' : 'sm:px-6'}`}>
        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : (
          <p className={`${isPublicView ? 'text-lg sm:text-xl leading-8' : 'text-lg sm:text-2xl leading-8 sm:leading-10'} font-medium text-gray-700`}>
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
    </div>
  );
}
