const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export interface Building {
  id: number;
  name: string;
  description?: string;
}

export interface BuildingSettings extends Building {
  default_too_cold: number;
  default_comfort: number;
  default_too_warm: number;
  default_temperature: number;
  default_humidity: number;
  default_co2: number;
  default_noise: number;
  default_light: number;
}

export interface BuildingVotes {
  id?: number;
  building_id: number;
  too_cold: number;
  comfort: number;
  too_warm: number;
  total: number;
  vote_date?: string;
  too_cold_percent: number;
  comfort_percent: number;
  too_warm_percent: number;
}

export interface SensorReading {
  building_id: number;
  temperature: number;
  humidity: number;
  co2: number;
  read_time: string;
  sensor_status?: SensorStatus;
}

export interface SensorStatus {
  interface_id: string;
  label: string;
  sensor_type: string;
  gpio_pin: number | null;
  source_building_id: number;
  source_building_name: string;
  driver_available: boolean;
  configured: boolean;
  mode: 'hardware' | 'fallback';
  last_read_success: boolean;
  checked_at: string;
  message: string;
  temperature?: number;
  humidity?: number;
  co2?: number;
}

export interface RaspberryPiHealth {
  service: string;
  checked_at: string;
  sensor_count: number;
  working_count: number;
  fallback_count: number;
  driver_available: boolean;
  network: {
    connected: boolean;
    hostname: string;
    local_ip: string | null;
    checked_at: string;
    message: string;
  };
  battery: {
    available: boolean;
    level_percent: number | null;
    state: string;
    checked_at: string;
    message: string;
  };
}

export interface RaspberryPiSensorListResponse {
  sensors: SensorStatus[];
}

export interface RaspberryPiSensorDetail {
  interface_id: string;
  label: string;
  temperature: number;
  humidity: number;
  co2: number;
  read_time: string;
  status: SensorStatus;
}

export interface StatsBuilding {
  id: number;
  name: string;
  tooCold: number;
  comfort: number;
  tooWarm: number;
  total: number;
  tooColdPercent: number;
  comfortPercent: number;
  tooWarmPercent: number;
}

export interface StatsResponse {
  currentBuilding: StatsBuilding | Record<string, never>;
  buildingRankings: StatsBuilding[];
}

export interface OperatorAuthChallenge {
  challenge_id: string;
  prompt: string;
  expires_in_seconds: number;
}

export interface OperatorAuthStatus {
  authenticated: boolean;
  username: string | null;
}

export interface ComfortAnalysisResponse {
  sampleSize: number;
  correlations: {
    temperature_to_comfort: number | null;
    humidity_to_comfort: number | null;
  };
  recommendation: {
    temperature: number | null;
    temperature_range: { min: number; max: number } | null;
    humidity: number | null;
    humidity_range: { min: number; max: number } | null;
    reference_defaults: {
      co2: number;
      noise: number;
      light: number;
    } | null;
  };
  buildingRecommendations: Array<{
    building_id: number;
    building_name: string;
    best_vote_date: string;
    comfort_percent: number;
    temperature: number | null;
    humidity: number | null;
  }>;
}

export interface SettingsResponse {
  buildings: BuildingSettings[];
  algorithmWeights: AlgorithmWeights;
}

export interface AlgorithmWeights {
  too_cold: number;
  comfort: number;
  too_warm: number;
  temp_factor: number;
}

export interface ChatSession {
  id: string;
  building_id: number | null;
  room_label: string;
  created_at: string;
  last_active_at: string;
}

export interface ChatMessageRecord {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
  created_at: string;
}

export interface ServiceRequestRecord {
  id: number;
  session_id: string;
  building_id: number | null;
  room_label: string;
  request_type: string;
  severity: string;
  summary: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryResponse {
  session: ChatSession;
  messages: ChatMessageRecord[];
  openRequests: ServiceRequestRecord[];
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  intent: string;
  service_request_created: boolean;
  service_request_id: number | null;
  service_summary: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') ?? '';
    let errorMessage = `Request failed with status ${response.status}`;

    if (contentType.includes('application/json')) {
      const errorJson = (await response.json()) as { error?: string; message?: string };
      errorMessage = errorJson.error ?? errorJson.message ?? errorMessage;
    } else {
      const errorText = await response.text();
      if (response.status === 404 && path.startsWith('/api/settings')) {
        errorMessage = 'Settings API not found. Restart the backend server so it loads the new settings routes.';
      } else if (errorText.trim()) {
        errorMessage = errorText.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
      }
    }

    throw new Error(errorMessage);
  }

  return response.json() as Promise<T>;
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...init,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim() || `Request failed with status ${response.status}`);
  }

  return response.blob();
}

export function getBuildings() {
  return request<Building[]>('/api/buildings');
}

export function getVotes(buildingName: string) {
  return request<BuildingVotes>(`/api/votes/${encodeURIComponent(buildingName)}`);
}

export function updateVotes(
  buildingId: number,
  payload: Pick<BuildingVotes, 'too_cold' | 'comfort' | 'too_warm' | 'total'>
) {
  return request<{ message: string; building_id: number }>(`/api/votes/${buildingId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getSensorData(buildingId: number) {
  return request<SensorReading>(`/api/sensor/${buildingId}`);
}

export function getStats() {
  return request<StatsResponse>('/api/stats');
}

export function getSettings() {
  return request<SettingsResponse>('/api/settings');
}

export function getOperatorAuthChallenge() {
  return request<OperatorAuthChallenge>('/api/operator/auth/challenge');
}

export function loginOperator(payload: {
  username: string;
  password: string;
  challenge_id: string;
  challenge_answer: string;
}) {
  return request<OperatorAuthStatus>('/api/operator/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getOperatorAuthStatus() {
  return request<OperatorAuthStatus>('/api/operator/auth/status');
}

export function logoutOperator() {
  return request<OperatorAuthStatus>('/api/operator/auth/logout', {
    method: 'POST',
  });
}

export function exportOperatorCsv() {
  return requestBlob('/api/operator/export.csv');
}

export function getComfortAnalysis() {
  return request<ComfortAnalysisResponse>('/api/operator/comfort-analysis');
}

export function getRaspberryPiHealth() {
  return request<RaspberryPiHealth>('/api/rpi/health');
}

export function getRaspberryPiSensors() {
  return request<RaspberryPiSensorListResponse>('/api/rpi/sensors');
}

export function getRaspberryPiSensorDetail(sensorId: string) {
  return request<RaspberryPiSensorDetail>(`/api/rpi/sensors/${encodeURIComponent(sensorId)}`);
}

export function createBuilding(payload: {
  name: string;
  description?: string;
  default_too_cold: number;
  default_comfort: number;
  default_too_warm: number;
  default_temperature: number;
  default_humidity: number;
  apply_today?: boolean;
}) {
  return request<{ message: string; building: Building }>('/api/settings/buildings', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateBuildingSettings(
  buildingId: number,
  payload: Partial<{
    name: string;
    description: string;
    default_too_cold: number;
    default_comfort: number;
    default_too_warm: number;
    default_temperature: number;
    default_humidity: number;
    default_co2: number;
    default_noise: number;
    default_light: number;
    apply_today: boolean;
  }>
) {
  return request<{ message: string }>(`/api/settings/buildings/${buildingId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteBuilding(buildingId: number) {
  return request<{ message: string; deleted_building_id: number }>(`/api/settings/buildings/${buildingId}`, {
    method: 'DELETE',
  });
}

export function updateAlgorithmWeights(payload: AlgorithmWeights) {
  return request<{ message: string; algorithmWeights: AlgorithmWeights }>('/api/settings/weights', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function createChatSession(payload: { building_id?: number; room_label?: string }) {
  return request<{ session_id: string }>('/api/chat/session', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getChatHistory(sessionId: string) {
  return request<ChatHistoryResponse>(`/api/chat/history/${sessionId}`);
}

export function sendChatMessage(payload: {
  session_id?: string;
  building_id?: number;
  room_label?: string;
  message: string;
}) {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function closeServiceRequest(requestId: number) {
  return request<{ message: string }>(`/api/chat/service-requests/${requestId}/close`, {
    method: 'POST',
  });
}

export function deleteChatMessage(messageId: number) {
  return request<{ message: string }>(`/api/chat/messages/${messageId}`, {
    method: 'DELETE',
  });
}
