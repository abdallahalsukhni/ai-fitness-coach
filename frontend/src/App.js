import { useState, useEffect, useCallback } from "react";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function App() {
  // ── Identity ────────────────────────────────────────────────
  const [userName, setUserName]     = useState(null);   // null = not loaded yet
  const [nameInput, setNameInput]   = useState("");
  const [showModal, setShowModal]   = useState(false);

  // ── Log state ──────────────────────────────────────────────
  const [workoutText, setWorkoutText] = useState("");
  const [logResult, setLogResult]     = useState(null);
  const [logError, setLogError]       = useState(false);
  const [logLoading, setLogLoading]   = useState(false);

  // ── Ask state ──────────────────────────────────────────────
  const [question, setQuestion]     = useState("");
  const [answer, setAnswer]         = useState(null);
  const [answerError, setAnswerError] = useState(false);
  const [askLoading, setAskLoading] = useState(false);

  // ── Recent workouts feed ───────────────────────────────────
  const [workouts, setWorkouts]     = useState([]);

  // ── On mount: check for saved user ────────────────────────
  useEffect(() => {
    const stored = localStorage.getItem("fitcoach_user");
    if (stored) {
      setUserName(stored);
    } else {
      setShowModal(true);
    }
  }, []);

  // userId derived from name (slug-safe)
  const userId = userName
    ? userName.toLowerCase().replace(/\s+/g, "_")
    : null;

  const saveName = () => {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    localStorage.setItem("fitcoach_user", trimmed);
    setUserName(trimmed);
    setShowModal(false);
  };

  // ── Fetch recent workouts ──────────────────────────────────
  const fetchWorkouts = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await fetch(`${API}/workouts?user_id=${userId}&limit=8`);
      const data = await res.json();
      setWorkouts(data.workouts || []);
    } catch {
      // silently fail — feed is non-critical
    }
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
      const res = await fetch(`${API}/log`, {
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
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, question }),
      });
      const data = await res.json();
      setAnswer(data.answer || "No response received.");
      setQuestion("");
    } catch {
      setAnswer("Could not reach server. Is FastAPI running?");
      setAnswerError(true);
    }
    setAskLoading(false);
  };

  const formatDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  // ── Don't render until we know if user is set ─────────────
  if (userName === null && !showModal) return null;

  return (
    <div className="app">

      {/* ── Name modal ── */}
      {showModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="logo-mark modal-logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
                   strokeLinecap="round" strokeLinejoin="round">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
              </svg>
            </div>
            <h2 className="modal-title">Welcome to FitCoach</h2>
            <p className="modal-sub">Enter your name to get started. Your workouts are saved to your profile.</p>
            <input
              className="modal-input"
              type="text"
              placeholder="Your name"
              value={nameInput}
              autoFocus
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveName()}
            />
            <button
              className="btn btn-primary modal-btn"
              onClick={saveName}
              disabled={!nameInput.trim()}
            >
              Get started →
            </button>
          </div>
        </div>
      )}

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
          {userName && (
            <span className="user-chip">{userName}</span>
          )}
        </div>
        <h1 className="header-title">
          Your workouts,<br /><strong>remembered.</strong>
        </h1>
        <p className="header-sub">
          Log in plain English. Ask anything about your history. Powered by your real data.
        </p>
      </header>

      {/* ── Two-column grid: Log + Recent ── */}
      <div className="grid">

        {/* Left: Log a workout */}
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

        {/* Right: Recent workouts feed */}
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
