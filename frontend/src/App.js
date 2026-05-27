import { useState, useEffect, useCallback } from "react";
import { supabase } from "./supabaseClient";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function App() {
  // ── Auth ───────────────────────────────────────────────────
  const [user, setUser]           = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    // Check for existing session on mount
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setAuthLoading(false);
    });

    // Keep state in sync with auth events (redirect back from Google, sign out, etc.)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signInWithGoogle = () => {
    supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  };

  const signOut = () => supabase.auth.signOut();

  // user.id is a UUID — safe, unique, used as user_id in the backend
  const userId = user?.id;

  // ── Log state ──────────────────────────────────────────────
  const [workoutText, setWorkoutText] = useState("");
  const [logResult, setLogResult]     = useState(null);
  const [logError, setLogError]       = useState(false);
  const [logLoading, setLogLoading]   = useState(false);

  // ── Ask state ──────────────────────────────────────────────
  const [question, setQuestion]       = useState("");
  const [answer, setAnswer]           = useState(null);
  const [answerError, setAnswerError] = useState(false);
  const [askLoading, setAskLoading]   = useState(false);

  // ── Recent workouts feed ───────────────────────────────────
  const [workouts, setWorkouts]       = useState([]);

  const fetchWorkouts = useCallback(async () => {
    if (!userId) return;
    try {
      const res  = await fetch(`${API}/workouts?user_id=${userId}&limit=8`);
      const data = await res.json();
      setWorkouts(data.workouts || []);
    } catch { /* silently fail */ }
  }, [userId]);

  useEffect(() => {
    if (userId) fetchWorkouts();
  }, [userId, fetchWorkouts]);

  // ── Log a workout ──────────────────────────────────────────
  const logWorkout = async () => {
    if (!workoutText.trim() || logLoading) return;
    setLogLoading(true);
    setLogResult(null);
    setLogError(false);
    try {
      const res  = await fetch(`${API}/log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, text: workoutText }),
      });
      const data = await res.json();
      setLogResult(data.preview || "Workout logged.");
      setWorkoutText("");
      fetchWorkouts();
    } catch {
      setLogResult("Could not save. Is the server running?");
      setLogError(true);
    }
    setLogLoading(false);
  };

  // ── Ask coach ──────────────────────────────────────────────
  const askQuestion = async () => {
    if (!question.trim() || askLoading) return;
    setAskLoading(true);
    setAnswer(null);
    setAnswerError(false);
    try {
      const res  = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, question }),
      });
      const data = await res.json();
      setAnswer(data.answer || "No response received.");
      setQuestion("");
    } catch {
      setAnswer("Could not reach server.");
      setAnswerError(true);
    }
    setAskLoading(false);
  };

  const formatDate = (iso) =>
    new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  // ── Loading splash (checking session) ─────────────────────
  if (authLoading) {
    return (
      <div className="auth-screen">
        <div className="logo-mark" style={{ width: 44, height: 44, borderRadius: 13 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
               strokeLinecap="round" strokeLinejoin="round" style={{ width: 22, height: 22 }}>
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
        </div>
      </div>
    );
  }

  // ── Sign-in screen ─────────────────────────────────────────
  if (!user) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <div className="logo-mark auth-logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
                 strokeLinecap="round" strokeLinejoin="round">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <h1 className="auth-title">FitCoach</h1>
          <p className="auth-sub">
            Log workouts in plain English.<br />Ask anything about your history.
          </p>
          <button className="btn-google" onClick={signInWithGoogle}>
            {/* Google "G" logo */}
            <svg viewBox="0 0 24 24" width="18" height="18">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  // ── Main app (authenticated) ───────────────────────────────
  return (
    <div className="app">

      {/* ── Header ── */}
      <header className="header">
        <div className="header-top">
          <div className="logo-row">
            <div className="logo-mark">
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
                   strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>
            <span className="logo-name">FitCoach</span>
          </div>
          <div className="header-user">
            {user.user_metadata?.avatar_url && (
              <img
                className="user-avatar"
                src={user.user_metadata.avatar_url}
                alt={user.user_metadata.full_name}
              />
            )}
            <span className="user-chip">{user.user_metadata?.full_name || user.email}</span>
            <button className="btn-signout" onClick={signOut}>Sign out</button>
          </div>
        </div>
        <h1 className="header-title">
          Your workouts,<br /><strong>remembered.</strong>
        </h1>
        <p className="header-sub">
          Log in plain English. Ask anything about your history. Powered by your real data.
        </p>
      </header>

      {/* ── Two-column grid ── */}
      <div className="grid">

        <div className="grid-col">
          <p className="section-label">Log a workout</p>
          <div className="input-box">
            <textarea
              rows={7}
              placeholder="e.g. Ran 5km in 28 minutes, then did 3 sets of 10 pull-ups..."
              value={workoutText}
              onChange={(e) => setWorkoutText(e.target.value)}
            />
            <div className="box-btn-row">
              <button
                className="btn btn-primary"
                onClick={logWorkout}
                disabled={logLoading || !workoutText.trim()}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {logLoading ? "Saving…" : "Log workout"}
              </button>
            </div>
          </div>
          {logResult && (
            <div className={`result ${logError ? "result-err" : "result-ok"}`}>
              <p className="result-tag">{logError ? "Error" : "Saved"}</p>
              <p className="result-body">{logResult}</p>
            </div>
          )}
        </div>

        <div className="grid-col">
          <p className="section-label">Recent workouts</p>
          <div className="feed-box">
            {workouts.length === 0 && (
              <p className="feed-empty">No workouts logged yet.</p>
            )}
            {workouts.map((w) => (
              <div className="feed-item" key={w.id}>
                <span className="feed-date">{formatDate(w.created_at)}</span>
                <p className="feed-text">{w.raw_text}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Ask your coach ── */}
      <div className="ask-section">
        <p className="section-label">Ask your coach</p>
        <div className="ask-input-wrap">
          <input
            type="text"
            placeholder="How has my bench press improved this month?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && askQuestion()}
          />
          <div className="box-btn-row">
            <button
              className="btn btn-primary"
              onClick={askQuestion}
              disabled={askLoading || !question.trim()}
            >
              {askLoading ? "Thinking…" : "Ask →"}
            </button>
          </div>
        </div>
        {askLoading && !answer && (
          <div className="result result-thinking">
            <p className="result-tag">Thinking</p>
            <div className="dots"><span /><span /><span /></div>
          </div>
        )}
        {answer && (
          <div className={`result ${answerError ? "result-err" : "result-thinking"}`}>
            <p className="result-tag">{answerError ? "Error" : "Coach"}</p>
            <p className="result-body">{answer}</p>
          </div>
        )}
      </div>
    </div>
  );
}
