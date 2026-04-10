import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { type StatsBuilding, getStats } from '@/api/ecoApi';
import { getSavedBuildingId, saveBuildingId } from '@/app/selection-context';
import { normalizeBuildingValue } from '@/app/url-context';

export function StatsPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [buildingData, setBuildingData] = useState<StatsBuilding[]>([]);
  const [currentBuilding, setCurrentBuilding] = useState<StatsBuilding | null>(null);
  const [error, setError] = useState('');
  const buildingParam = searchParams.get('building');
  const isPublicView = location.pathname.startsWith('/user');

  function updateBuildingSearchParam(building: StatsBuilding | null) {
    const nextParams = new URLSearchParams(searchParams);
    if (building) {
      nextParams.set('building', building.name);
    } else {
      nextParams.delete('building');
    }
    setSearchParams(nextParams, { replace: true });
  }

  useEffect(() => {
    let cancelled = false;

    async function loadStats() {
      try {
        setError('');
        const stats = await getStats();
        if (cancelled) {
          return;
        }

        setBuildingData(stats.buildingRankings);
        const preferredBuilding = buildingParam
          ? stats.buildingRankings.find(
              (building) => normalizeBuildingValue(building.name) === normalizeBuildingValue(buildingParam)
            ) ?? null
          : null;
        const savedBuildingId = getSavedBuildingId(isPublicView);
        const savedBuilding =
          savedBuildingId === null
            ? null
            : stats.buildingRankings.find((building) => building.id === savedBuildingId) ?? null;
        setCurrentBuilding(
          preferredBuilding ??
            savedBuilding ??
            (Object.keys(stats.currentBuilding).length > 0
              ? (stats.currentBuilding as StatsBuilding)
              : stats.buildingRankings[0] ?? null)
        );
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load stats');
        }
      }
    }

    loadStats();
    const intervalId = window.setInterval(() => {
      loadStats();
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [buildingParam, isPublicView]);

  useEffect(() => {
    saveBuildingId(isPublicView, currentBuilding?.id ?? null);
  }, [currentBuilding, isPublicView]);

  useEffect(() => {
    if (!currentBuilding) {
      return;
    }

    if (buildingParam === currentBuilding.name) {
      return;
    }

    updateBuildingSearchParam(currentBuilding);
  }, [currentBuilding, buildingParam]);

  if (error) {
    return <div className="flex h-full items-center justify-center bg-white text-red-600">{error}</div>;
  }

  if (!currentBuilding) {
    return <div className="flex h-full items-center justify-center bg-white text-gray-600">Loading campus stats...</div>;
  }

  return (
    <div className="h-full min-h-0 bg-white">
      <div className="h-full min-h-0 overflow-y-auto">
      <div className={`min-h-full bg-white grid grid-cols-1 ${isPublicView ? 'xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]' : 'xl:grid-cols-[minmax(360px,460px)_minmax(0,1fr)]'}`}>
        <div className={`flex flex-col border-b border-gray-200 ${isPublicView ? 'xl:border-b-0 xl:border-r' : 'xl:border-b-0 xl:border-r'} border-gray-200`}>
          <div className={`bg-green-600 text-white text-center px-4 py-4 ${isPublicView ? '' : 'sm:py-5'}`}>
          <h2 className="text-xl font-bold">Current Vote Status</h2>
          <p className="text-sm opacity-90 mt-1">{currentBuilding.name}</p>
          </div>

          <div className={`flex-1 flex flex-col items-center bg-gradient-to-b from-green-50 to-white ${isPublicView ? 'p-4' : 'p-4 sm:p-6'}`}>
            <div className="w-full max-w-sm space-y-4">
            <div className="bg-blue-400 text-white rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-3xl">❄️</span>
                  <span className="text-xl font-bold">Too Cold</span>
                </div>
                <div className="text-4xl font-bold">{currentBuilding.tooCold}</div>
              </div>
              <div className="mt-2 bg-white/20 rounded-full h-2">
                <div className="bg-white h-2 rounded-full transition-all duration-500" style={{ width: `${currentBuilding.tooColdPercent}%` }} />
              </div>
              <div className="text-right mt-1 text-sm">{currentBuilding.tooColdPercent}%</div>
            </div>

            <div className="bg-green-500 text-white rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-3xl">☀️</span>
                  <span className="text-xl font-bold">Comfort</span>
                </div>
                <div className="text-4xl font-bold">{currentBuilding.comfort}</div>
              </div>
              <div className="mt-2 bg-white/20 rounded-full h-2">
                <div className="bg-white h-2 rounded-full transition-all duration-500" style={{ width: `${currentBuilding.comfortPercent}%` }} />
              </div>
              <div className="text-right mt-1 text-sm">{currentBuilding.comfortPercent}%</div>
            </div>

            <div className="bg-orange-500 text-white rounded-2xl p-5 shadow-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-3xl">🔥</span>
                  <span className="text-xl font-bold">Too Warm</span>
                </div>
                <div className="text-4xl font-bold">{currentBuilding.tooWarm}</div>
              </div>
              <div className="mt-2 bg-white/20 rounded-full h-2">
                <div className="bg-white h-2 rounded-full transition-all duration-500" style={{ width: `${currentBuilding.tooWarmPercent}%` }} />
              </div>
              <div className="text-right mt-1 text-sm">{currentBuilding.tooWarmPercent}%</div>
            </div>

            <div className="text-center pt-4 border-t-2 border-gray-200">
              <div className="text-gray-600 text-base">Total Votes Today</div>
              <div className="text-4xl font-bold text-gray-800 mt-1">{currentBuilding.total}</div>
            </div>
          </div>
        </div>
      </div>

        <div className="flex flex-col min-h-0">
          <div className={`bg-blue-600 text-white text-center px-4 py-4 ${isPublicView ? '' : 'sm:py-5'}`}>
          <h2 className="text-xl font-bold">Campus Vote Rankings</h2>
          <p className="text-sm opacity-90 mt-1">Comfort Level by Building</p>
          </div>

          <div className={`bg-gradient-to-b from-blue-50 to-white ${isPublicView ? 'p-4' : 'p-4 sm:p-6'}`}>
            <div className="space-y-3">
              {buildingData.map((building, index) => (
                <button
                  key={building.id}
                  type="button"
                  onClick={() => {
                    setCurrentBuilding(building);
                    updateBuildingSearchParam(building);
                  }}
                  className={`w-full text-left bg-white rounded-2xl p-5 shadow-md border-2 ${
                    building.id === currentBuilding.id ? 'border-green-500' : 'border-gray-200'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2 gap-3">
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-white text-sm ${
                          index === 0 ? 'bg-yellow-400' : index === 1 ? 'bg-gray-400' : index === 2 ? 'bg-orange-400' : 'bg-gray-300'
                        }`}
                      >
                        {index + 1}
                      </div>
                      <div>
                        <div className="font-semibold text-gray-800 text-sm">{building.name}</div>
                        <div className="text-xs text-gray-500">{building.total} total votes</div>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xl font-bold text-green-600">{building.comfortPercent}%</div>
                      <div className="text-xs text-gray-500">comfort</div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3 text-xs mb-2">
                    <div className="flex items-center gap-1 text-blue-500">
                      <span>❄️</span>
                      <span className="font-medium">{building.tooCold}</span>
                    </div>
                    <div className="flex items-center gap-1 text-green-600">
                      <span>☀️</span>
                      <span className="font-medium">{building.comfort}</span>
                    </div>
                    <div className="flex items-center gap-1 text-orange-600">
                      <span>🔥</span>
                      <span className="font-medium">{building.tooWarm}</span>
                    </div>
                  </div>

                  <div className="flex h-2 rounded-full overflow-hidden">
                    <div className="bg-blue-400 transition-all duration-500" style={{ width: `${building.tooColdPercent}%` }} />
                    <div className="bg-green-500 transition-all duration-500" style={{ width: `${building.comfortPercent}%` }} />
                    <div className="bg-orange-500 transition-all duration-500" style={{ width: `${building.tooWarmPercent}%` }} />
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
