import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  getOperatorAuthChallenge,
  getOperatorAuthStatus,
  loginOperator,
} from '@/api/ecoApi';

export function OperatorLoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [challengeId, setChallengeId] = useState('');
  const [challengePrompt, setChallengePrompt] = useState('');
  const [challengeAnswer, setChallengeAnswer] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function refreshChallenge() {
    const challenge = await getOperatorAuthChallenge();
    setChallengeId(challenge.challenge_id);
    setChallengePrompt(challenge.prompt);
    setChallengeAnswer('');
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const authStatus = await getOperatorAuthStatus();
        if (authStatus.authenticated) {
          navigate('/', { replace: true });
          return;
        }
      } catch {
        // Ignore and fall back to login flow.
      }

      try {
        await refreshChallenge();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Failed to load anti-attack code');
      }
    }

    bootstrap();
  }, [navigate]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError('');

    try {
      await loginOperator({
        username,
        password,
        challenge_id: challengeId,
        challenge_answer: challengeAnswer,
      });
      navigate('/', { replace: true });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to log in');
      try {
        await refreshChallenge();
      } catch {
        // Keep the original login error visible.
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 px-4 py-8 flex items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-md rounded-3xl bg-white border border-gray-200 shadow-xl p-6 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Operator Login</h1>
          <p className="mt-1 text-sm text-gray-600">
            Sign in to access the operator dashboard, CSV export, and comfort analysis tools.
          </p>
        </div>

        {error ? <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <label className="block text-sm text-gray-700">
          <span className="mb-1 block">Username</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            className="w-full rounded-xl border border-gray-300 px-3 py-2"
            autoComplete="username"
          />
        </label>

        <label className="block text-sm text-gray-700">
          <span className="mb-1 block">Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-xl border border-gray-300 px-3 py-2"
            autoComplete="current-password"
          />
        </label>

        <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
          <div className="text-sm font-semibold text-gray-900">Anti-attack code</div>
          <div className="mt-1 text-sm text-gray-600">{challengePrompt || 'Loading challenge...'}</div>
        </div>

        <label className="block text-sm text-gray-700">
          <span className="mb-1 block">Answer</span>
          <input
            value={challengeAnswer}
            onChange={(event) => setChallengeAnswer(event.target.value)}
            className="w-full rounded-xl border border-gray-300 px-3 py-2"
            inputMode="numeric"
          />
        </label>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={refreshChallenge}
            className="rounded-xl border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
          >
            Refresh Code
          </button>
          <button
            type="submit"
            disabled={isSubmitting || !challengeId}
            className="flex-1 rounded-xl bg-gray-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {isSubmitting ? 'Signing In...' : 'Sign In'}
          </button>
        </div>
      </form>
    </div>
  );
}
