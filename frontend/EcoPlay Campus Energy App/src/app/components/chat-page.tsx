import { useEffect, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { Send, Bot, Trash2, PlusSquare } from 'lucide-react';
import { BUILDINGS_UPDATED_EVENT } from '@/app/building-events';
import { getBuildingFromParam } from '@/app/url-context';
import {
  type Building,
  type ChatMessageRecord,
  type ServiceRequestRecord,
  closeServiceRequest,
  createChatSession,
  deleteChatMessage,
  getBuildings,
  getChatHistory,
  sendChatMessage,
} from '@/api/ecoApi';

const SESSION_STORAGE_KEY = 'ecoplay_chat_session_id';

export function ChatPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [selectedBuildingId, setSelectedBuildingId] = useState<number | null>(null);
  const [roomLabel, setRoomLabel] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<ChatMessageRecord[]>([]);
  const [openRequests, setOpenRequests] = useState<ServiceRequestRecord[]>([]);
  const [input, setInput] = useState('');
  const [statusMessage, setStatusMessage] = useState('Smart chat can help explain comfort data and create service requests from room issues.');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const buildingParam = searchParams.get('building');
  const roomParam = searchParams.get('room');
  const isPublicView = location.pathname.startsWith('/user');
  const hasPresetBuilding = Boolean(buildingParam);
  const hasPresetRoom = Boolean(roomParam);
  const selectedBuilding = buildings.find((building) => building.id === selectedBuildingId) ?? null;

  function resetChatSession(nextBuildingId: number | null) {
    setSessionId('');
    setMessages([]);
    setOpenRequests([]);
    setError('');
    setStatusMessage('Smart chat can help explain comfort data and create service requests from room issues.');
    if (nextBuildingId !== null) {
      setSelectedBuildingId(nextBuildingId);
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    if (!hasPresetRoom) {
      setRoomLabel('');
    }
  }

  async function refreshBuildings(preferredBuildingId?: number | null) {
    const buildingList = await getBuildings();
    setBuildings(buildingList);

    if (buildingList.length === 0) {
      resetChatSession(null);
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

    if (!buildingList.some((building) => building.id === selectedBuildingId)) {
      resetChatSession(nextSelectedId);
      return;
    }

    setSelectedBuildingId(nextSelectedId);
  }

  useEffect(() => {
    let cancelled = false;

    async function loadInitialData() {
      try {
        const buildingList = await getBuildings();
        if (cancelled) {
          return;
        }

        setBuildings(buildingList);
        const buildingFromUrl = getBuildingFromParam(buildingList, buildingParam);
        if (buildingList.length > 0) {
          setSelectedBuildingId(buildingFromUrl?.id ?? buildingList[0].id);
        }
        if (roomParam) {
          setRoomLabel(roomParam);
        }

        const savedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
        if (savedSessionId) {
          try {
            const history = await getChatHistory(savedSessionId);
            if (cancelled) {
              return;
            }
            setSessionId(savedSessionId);
            setMessages(history.messages);
            setOpenRequests(history.openRequests);
            setRoomLabel(roomParam ?? history.session.room_label ?? '');
            if (buildingFromUrl?.id) {
              setSelectedBuildingId(buildingFromUrl.id);
            } else if (history.session.building_id) {
              setSelectedBuildingId(history.session.building_id);
            }
          } catch {
            window.localStorage.removeItem(SESSION_STORAGE_KEY);
          }
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load chat context');
        }
      }
    }

    loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [buildingParam, roomParam]);

  useEffect(() => {
    async function handleBuildingsUpdated() {
      try {
        await refreshBuildings(selectedBuildingId);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Failed to refresh buildings');
      }
    }

    window.addEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    return () => {
      window.removeEventListener(BUILDINGS_UPDATED_EVENT, handleBuildingsUpdated);
    };
  }, [selectedBuildingId, buildings, sessionId, messages, buildingParam]);

  async function ensureSessionId() {
    if (sessionId) {
      return sessionId;
    }

    const response = await createChatSession({
      building_id: selectedBuildingId ?? undefined,
      room_label: roomLabel,
    });
    setSessionId(response.session_id);
    window.localStorage.setItem(SESSION_STORAGE_KEY, response.session_id);
    return response.session_id;
  }

  async function handleSend() {
    if (!input.trim() || isSending) {
      return;
    }

    const content = input.trim();
    setInput('');
    setError('');
    setIsSending(true);

    const optimisticUserMessage: ChatMessageRecord = {
      id: Date.now(),
      session_id: sessionId || 'pending',
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, optimisticUserMessage]);

    try {
      const activeSessionId = await ensureSessionId();
      const response = await sendChatMessage({
        session_id: activeSessionId,
        building_id: selectedBuildingId ?? undefined,
        room_label: roomLabel,
        message: content,
      });

      const history = await getChatHistory(response.session_id);
      setSessionId(response.session_id);
      window.localStorage.setItem(SESSION_STORAGE_KEY, response.session_id);
      setMessages(history.messages);
      setOpenRequests(history.openRequests);

      if (response.service_request_created) {
        setStatusMessage(
          response.service_summary
            ? `Service request created: ${response.service_summary}`
            : 'A service request was created from this conversation.'
        );
      } else {
        setStatusMessage('Smart chat is active and using your current building context.');
      }
    } catch (sendError) {
      setMessages((current) => current.filter((message) => message.id !== optimisticUserMessage.id));
      setError(sendError instanceof Error ? sendError.message : 'Failed to send chat message');
    } finally {
      setIsSending(false);
    }
  }

  async function handleCloseRequest(requestId: number) {
    try {
      setError('');
      await closeServiceRequest(requestId);
      setOpenRequests((current) => current.filter((request) => request.id !== requestId));
      setStatusMessage('Service request closed.');
    } catch (closeError) {
      setError(closeError instanceof Error ? closeError.message : 'Failed to close service request');
    }
  }

  function handleBuildingChange(nextBuildingId: number) {
    if (!sessionId && messages.length === 0) {
      setSelectedBuildingId(nextBuildingId);
      return;
    }

    const confirmed = window.confirm(
      'Changing the building will start a new chat session and clear the current conversation. Do you want to continue?'
    );

    if (!confirmed) {
      return;
    }

    resetChatSession(nextBuildingId);
  }

  async function handleDeleteMessage(messageId: number) {
    try {
      setError('');
      await deleteChatMessage(messageId);
      if (sessionId) {
        const history = await getChatHistory(sessionId);
        const stillExists = history.messages.some((message) => message.id === messageId);
        if (stillExists) {
          throw new Error(`Backend did not remove chat message id ${messageId} from the database.`);
        }
        setMessages(history.messages);
        setOpenRequests(history.openRequests);
      } else {
        setMessages((current) => current.filter((message) => message.id !== messageId));
      }
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Failed to delete chat message');
    }
  }

  function handleNewChat() {
    if (!sessionId && messages.length === 0) {
      return;
    }
    const confirmed = window.confirm(
      'Start a new chat? This will clear the current conversation and open requests from this screen.'
    );
    if (!confirmed) {
      return;
    }
    resetChatSession(selectedBuildingId);
    if (!hasPresetRoom) {
      setRoomLabel('');
    }
  }

  return (
    <div className="flex flex-col h-full bg-white">
      <div className={`border-b ${isPublicView ? 'bg-gradient-to-b from-green-600 to-green-500 text-white px-4 py-5' : 'bg-green-600 text-white px-4 py-4 sm:px-5 sm:py-5'}`}>
        <div className={`flex ${isPublicView ? 'flex-col items-stretch gap-3 text-center' : 'flex-col gap-3 lg:flex-row lg:items-center lg:justify-between lg:gap-4'}`}>
          <div>
            <h1 className={`${isPublicView ? 'text-2xl' : 'text-xl sm:text-2xl'} font-bold`}>AI Energy Assistant</h1>
            {isPublicView ? (
              <p className="mt-2 text-sm text-green-50">
                Share comfort issues or questions and we will log them for follow-up.
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={handleNewChat}
            className={`inline-flex items-center justify-center gap-2 rounded-xl border border-white/30 bg-white/10 px-3 py-2 text-sm font-semibold text-white hover:bg-white/20 ${isPublicView ? 'w-full' : 'w-full lg:w-auto'}`}
          >
            <PlusSquare className="h-4 w-4" />
            New Chat
          </button>
        </div>
        <div className={`mt-3 ${isPublicView ? 'space-y-3' : 'grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_220px] xl:grid-cols-[minmax(0,1fr)_220px_220px] items-center'}`}>
          <p className={`text-sm ${isPublicView ? 'text-green-50 text-center' : 'text-green-50'}`}>{statusMessage}</p>
          {isPublicView ? (
            <div className="grid grid-cols-1 gap-2 text-left">
              <label className="block">
                <span className="sr-only">Building</span>
                <select
                  value={selectedBuildingId ?? ''}
                  onChange={(event) => handleBuildingChange(Number(event.target.value))}
                  className="w-full rounded-2xl px-4 py-3 text-sm text-gray-900"
                >
                  {buildings.map((building) => (
                    <option key={building.id} value={building.id}>
                      {building.name}
                    </option>
                  ))}
                </select>
              </label>
              <input
                value={roomLabel}
                onChange={(event) => setRoomLabel(event.target.value)}
                placeholder="Room / Area"
                className="w-full rounded-2xl px-4 py-3 text-sm text-gray-900"
              />
            </div>
          ) : (
            <>
              <select
                value={selectedBuildingId ?? ''}
                onChange={(event) => handleBuildingChange(Number(event.target.value))}
                className="w-full rounded-lg px-3 py-2 text-sm text-gray-900"
              >
                {buildings.map((building) => (
                  <option key={building.id} value={building.id}>
                    {building.name}
                  </option>
                ))}
              </select>
              <input
                value={roomLabel}
                onChange={(event) => setRoomLabel(event.target.value)}
                placeholder="Room / Area"
                className="w-full rounded-lg px-3 py-2 text-sm text-gray-900"
              />
            </>
          )}
        </div>
      </div>

      <div className={`flex-1 overflow-y-auto space-y-4 ${isPublicView ? 'bg-slate-50 px-4 py-4' : 'bg-gray-50 px-4 py-4'}`}>
        {error ? <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        {openRequests.length > 0 ? (
          <div className={`rounded-2xl bg-amber-50 border border-amber-200 px-4 py-3 ${isPublicView ? 'shadow-sm' : ''}`}>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-amber-900">Open Service Requests</h2>
              <span className="text-xs text-amber-700">{openRequests.length} active</span>
            </div>
            <div className="mt-3 space-y-2">
              {openRequests.map((request) => (
                <div key={request.id} className="rounded-xl bg-white border border-amber-100 px-3 py-3">
                  <div className={`flex items-start gap-3 ${isPublicView ? 'flex-col' : 'flex-col xl:flex-row xl:justify-between'}`}>
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        #{request.id} · {request.request_type.replaceAll('_', ' ')}
                      </div>
                      <div className="text-xs text-gray-500">
                        Severity: {request.severity} {request.room_label ? `· ${request.room_label}` : ''}
                      </div>
                      <p className="mt-1 text-sm text-gray-700">{request.summary}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCloseRequest(request.id)}
                      className={`rounded-lg border border-gray-300 px-3 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-50 ${isPublicView ? 'w-full' : ''}`}
                    >
                      Close
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {messages.length === 0 ? (
          <div className={`rounded-2xl border border-dashed border-gray-300 bg-white px-5 py-4 text-sm text-gray-600 ${isPublicView ? 'shadow-sm' : ''}`}>
            Ask about room comfort, building conditions, or describe a problem like “Room 301 is too cold every afternoon.”
          </div>
        ) : null}

        {messages.map((message) => (
          <div key={`${message.role}-${message.id}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex gap-2 ${isPublicView ? 'max-w-[92%]' : 'max-w-[82%]'} ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${message.role === 'assistant' ? 'bg-green-600' : 'bg-blue-600'}`}>
                {message.role === 'assistant' ? <Bot className="w-5 h-5 text-white" /> : <span className="text-white font-bold">U</span>}
              </div>
              <div
                className={`rounded-2xl px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-white text-gray-800 border border-green-200 shadow-sm'
                }`}
              >
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                <div className={`mt-2 flex ${message.role === 'user' ? 'justify-start' : 'justify-end'}`}>
                  <button
                    type="button"
                    onClick={() => handleDeleteMessage(message.id)}
                    className={`inline-flex items-center gap-1 text-xs ${
                      message.role === 'user' ? 'text-blue-100 hover:text-white' : 'text-gray-500 hover:text-gray-800'
                    }`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={`border-t border-gray-200 bg-white ${isPublicView ? 'p-3' : 'p-4'}`}>
        <div className="flex gap-2 items-end">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                handleSend();
              }
            }}
            placeholder="Describe the room issue or ask for help..."
            className={`flex-1 border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 ${isPublicView ? 'px-4 py-3.5 text-base' : 'px-4 py-3'}`}
          />
          <button
            onClick={handleSend}
            disabled={isSending}
            className={`bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white rounded-full transition-colors ${isPublicView ? 'p-3.5' : 'p-3'}`}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
