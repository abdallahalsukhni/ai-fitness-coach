import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "./supabaseClient";
import "./App.css";

const API = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

export default function App() {
  // ── Auth ───────────────────────────────────────────────────
  const [user, setUser]               = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setAuthLoading(false);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  const signInWithGoogle = () =>
    supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin } });

  const signOut = () => supabase.auth.signOut();
  const userId  = user?.id;

  // ── Log ────────────────────────────────────────────────────
  const [workoutText, setWorkoutText] = useState("");
  const [logResult, setLogResult]     = useState(null);
  const [logError, setLogError]       = useState(false);
  const [logLoading, setLogLoading]   = useState(false);

  // ── Ask ────────────────────────────────────────────────────
  const [question, setQuestion]   = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [messages, setMessages]   = useState([]); // { role:"user"|"coach", content, meta?, error? }
  const [history, setHistory]     = useState([]); // { role:"user"|"assistant", content } sent to backend
  const threadRef                 = useRef(null);

  // ── Feed ───────────────────────────────────────────────────
  const [workouts, setWorkouts] = useState([]);

  // ── Stats ──────────────────────────────────────────────────
  const [stats, setStats] = useState(null);

  const fetchWorkouts = useCallback(async () => {
    if (!userId) return;
    try {
      const res  = await fetch(`${API}/workouts?user_id=${userId}&limit=8`);
      const data = await res.json();
      setWorkouts(data.workouts || []);
    } catch {}
  }, [userId]);

  const fetchStats = useCallback(async () => {
    if (!userId) return;
    try {
      const res  = await fetch(`${API}/stats?user_id=${userId}`);
      const data = await res.json();
      setStats(data);
    } catch {}
  }, [userId]);

  useEffect(() => {
    if (userId) { fetchWorkouts(); fetchStats(); }
  }, [userId, fetchWorkouts, fetchStats]);

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
      fetchStats();
    } catch {
      setLogResult("Could not save. Is the server running?");
      setLogError(true);
    }
    setLogLoading(false);
  };

  // Auto-scroll thread to bottom on new messages
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, askLoading]);

  const clearConversation = () => { setMessages([]); setHistory([]); };

  const askQuestion = async () => {
    if (!question.trim() || askLoading) return;
    const q = question;
    setQuestion("");
    setAskLoading(true);

    setMessages(prev => [...prev, { role: "user", content: q }]);

    try {
      const res  = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, question: q, history }),
      });
      const data = await res.json();
      const text = data.answer || "No response received.";
      const meta = { pipeline: data.pipeline || "RAG", steps: data.steps || 1 };

      setMessages(prev => [...prev, { role: "coach", content: text, meta }]);
      setHistory(prev => [
        ...prev,
        { role: "user", content: q },
        { role: "assistant", content: text },
      ].slice(-12));
    } catch {
      setMessages(prev => [...prev, { role: "coach", content: "Could not reach server.", error: true }]);
    }
    setAskLoading(false);
  };

  const deleteWorkout = async (workoutId) => {
    try {
      await fetch(`${API}/workouts/${workoutId}?user_id=${userId}`, { method: "DELETE" });
      fetchWorkouts();
      fetchStats();
    } catch {}
  };

  const formatDate = (iso) =>
    new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  const todayLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric",
  });

  const firstName = user?.user_metadata?.full_name?.split(" ")[0] || "";

  const Logo = () => (
    <div className="logo-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
           strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    </div>
  );

  // ── Loading ────────────────────────────────────────────────
  if (authLoading) return <div className="splash"><Logo /></div>;

  // ── Sign-in ────────────────────────────────────────────────
  if (!user) return (
    <div className="auth-screen">
      <div className="auth-center">
        <div className="auth-brand-row">
          <Logo />
          <span className="auth-brand-name">FitCoach</span>
        </div>

        <h1 className="auth-title">Your workouts,<br /><strong>remembered.</strong></h1>
        <p className="auth-sub">Log workouts in plain English. Ask anything about your history. Powered by real AI, not guesswork.</p>

        <div className="auth-features">
          <div className="auth-feature"><div className="auth-feature-dot" />Log anything — no forms or dropdowns</div>
          <div className="auth-feature"><div className="auth-feature-dot" />Semantic search across your full history</div>
          <div className="auth-feature"><div className="auth-feature-dot" />AI coach answers grounded in your real data</div>
        </div>

        <button className="btn-google" onClick={signInWithGoogle}>
          <svg viewBox="0 0 24 24" width="20" height="20">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>
        <p className="auth-legal">Your data is private and only visible to you.</p>
      </div>
    </div>
  );

  // ── Main app ───────────────────────────────────────────────
  return (
    <div className="layout">

      {/* Sticky nav */}
      <header className="nav">
        <div className="nav-inner">
          <div className="nav-left">
            <Logo />
            <span className="nav-brand">FitCoach</span>
          </div>
          <div className="nav-right">
            {user.user_metadata?.avatar_url && (
              <img className="user-avatar" src={user.user_metadata.avatar_url} alt="" />
            )}
            <span className="nav-name">{user.user_metadata?.full_name || user.email}</span>
            <button className="btn-signout" onClick={signOut}>Sign out</button>
          </div>
        </div>
      </header>

      <main className="main">

        {/* Greeting bar */}
        <div className="greeting-bar">
          <div className="greeting-left">
            <p className="greeting-text">{greeting()}{firstName ? `, ${firstName}` : ""}.</p>
            <p className="greeting-date">{todayLabel}</p>
          </div>
          {stats && (
            <div className="greeting-stats">
              <div className="stat">
                <span className="stat-value">{stats.total_workouts}</span>
                <span className="stat-label">Total workouts</span>
              </div>
              <div className="stat-divider" />
              <div className="stat">
                <span className="stat-value">{stats.this_week}</span>
                <span className="stat-label">This week</span>
              </div>
            </div>
          )}
        </div>

        {/* Log + Recent grid */}
        <div className="grid">
          <div className="card">
            <p className="section-label">Log a workout</p>
            <textarea
              className="workout-input"
              placeholder="e.g. Ran 5km in 28 minutes, then did 3 sets of 10 pull-ups and 4 sets of bench at 80kg..."
              value={workoutText}
              onChange={(e) => setWorkoutText(e.target.value)}
            />
            <div className="card-footer">
              <button
                className="btn btn-primary"
                onClick={logWorkout}
                disabled={logLoading || !workoutText.trim()}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                     strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
                {logLoading ? "Saving…" : "Log workout"}
              </button>
            </div>
            {logResult && (
              <div className={`toast ${logError ? "toast-err" : "toast-ok"}`}>
                <span className="toast-label">{logError ? "Error" : "Saved"}</span>
                {logResult}
              </div>
            )}
          </div>

          <div className="card card-feed">
            <p className="section-label">Recent workouts</p>
            <div className="feed">
              {workouts.length === 0
                ? <p className="feed-empty">No workouts yet — log your first one.</p>
                : workouts.map((w) => (
                    <div className="feed-item" key={w.id}>
                      <div className="feed-item-header">
                        <span className="feed-date">{formatDate(w.created_at)}</span>
                        <button
                          className="btn-delete"
                          onClick={() => deleteWorkout(w.id)}
                          title="Delete workout"
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                               strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6l-1 14H6L5 6" />
                            <path d="M10 11v6M14 11v6" />
                            <path d="M9 6V4h6v2" />
                          </svg>
                        </button>
                      </div>
                      <p className="feed-text">{w.raw_text}</p>
                    </div>
                  ))
              }
            </div>
          </div>
        </div>

        {/* Ask */}
        <div className="ask-card">
          <div className="ask-card-header">
            <p className="section-label">Ask your coach</p>
            {messages.length > 0 && (
              <button className="btn-clear-convo" onClick={clearConversation}>Clear</button>
            )}
          </div>

          {(messages.length > 0 || askLoading) && (
            <div className="convo-thread" ref={threadRef}>
              {messages.map((msg, i) =>
                msg.role === "user" ? (
                  <div className="convo-user" key={i}>
                    <span className="convo-label">You</span>
                    <p className="convo-user-text">{msg.content}</p>
                  </div>
                ) : (
                  <div className="convo-coach" key={i}>
                    <div className="answer-header">
                      <span className="answer-label">{msg.error ? "Error" : "Coach"}</span>
                      {!msg.error && msg.meta && (
                        <span className={`pipeline-badge ${msg.meta.pipeline === "RLM" ? "pipeline-rlm" : "pipeline-rag"}`}>
                          {msg.meta.pipeline === "RLM"
                            ? `RLM · ${msg.meta.steps} retrieval step${msg.meta.steps !== 1 ? "s" : ""}`
                            : "RAG"}
                        </span>
                      )}
                    </div>
                    <p className="answer-text">{msg.content}</p>
                  </div>
                )
              )}
              {askLoading && (
                <div className="convo-coach">
                  <div className="answer-header">
                    <span className="answer-label">Thinking</span>
                  </div>
                  <div className="dots"><span /><span /><span /></div>
                </div>
              )}
            </div>
          )}

          <div className="ask-row">
            <input
              className="ask-input"
              type="text"
              placeholder="How has my bench press improved this month?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && askQuestion()}
            />
            <button
              className="btn btn-primary ask-btn"
              onClick={askQuestion}
              disabled={askLoading || !question.trim()}
            >
              Ask →
            </button>
          </div>
        </div>

        {/* How it works */}
        <div className="how-section">
          <p className="section-label">Under the hood</p>
          <div className="how-grid">
            <div className="how-card">
              <div className="how-num">CHUNK</div>
              <h3 className="how-title">Contextual chunking</h3>
              <p className="how-body">
                Every chunk gets a Claude-generated context sentence prepended before
                embedding. A chunk reading "increased weight to 90kg" becomes "This is
                from a chest session where tricep work preceded the bench press —
                increased weight to 90kg." Exercise order, session type, and pre-fatigue
                context are encoded in the vector, not lost at the chunk boundary.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">HYBRID</div>
              <h3 className="how-title">Hybrid retrieval + reranking</h3>
              <p className="how-body">
                Each question runs two searches in parallel — pgvector cosine similarity
                for semantic matches and Postgres BM25 full-text search for exact keyword
                matches — then merges both ranked lists with Reciprocal Rank Fusion. A
                cross-encoder reranker reads the query and each candidate together in one
                forward pass, scoring 20 candidates down to 5 by actual relevance, not
                just vector distance.
              </p>
            </div>
            <div className="how-card">
              <div className="how-num">RLM</div>
              <h3 className="how-title">Recursive retrieval loop</h3>
              <p className="how-body">
                Complex analytical questions trigger a loop: the model decides what to
                search for next, retrieves and distills findings across up to 5 steps,
                then synthesizes a final answer from all collected evidence — not raw
                chunks. Every answer shows a pipeline badge: <code>RAG</code> for
                single-pass, <code>RLM · N steps</code> for recursive.
              </p>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
