import { useState } from "react";
import axios from "axios";

const API = "http://127.0.0.1:8000";
const USER_ID = "user_1";

function App() {
  const [workoutText, setWorkoutText] = useState("");
  const [question, setQuestion] = useState("");
  const [logResult, setLogResult] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);

  const logWorkout = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/log`, {
        user_id: USER_ID,
        text: workoutText,
      });
      setLogResult(res.data.summary);
      setWorkoutText("");
    } catch (err) {
      setLogResult("Error logging workout.");
    }
    setLoading(false);
  };

  const askQuestion = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/ask`, {
        user_id: USER_ID,
        question: question,
      });
      setAnswer(res.data.answer);
      setQuestion("");
    } catch (err) {
      setAnswer("Error getting answer.");
    }
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 600, margin: "60px auto", fontFamily: "sans-serif", padding: "0 20px" }}>
      <h1>AI Fitness Coach</h1>

      <section style={{ marginBottom: 40 }}>
        <h2>Log a Workout</h2>
        <textarea
          rows={4}
          style={{ width: "100%", padding: 10, fontSize: 14 }}
          placeholder="e.g. Ran 5km in 28 minutes, then did 3 sets of 10 pull-ups"
          value={workoutText}
          onChange={(e) => setWorkoutText(e.target.value)}
        />
        <button
          onClick={logWorkout}
          disabled={loading || !workoutText}
          style={{ marginTop: 10, padding: "10px 20px", cursor: "pointer" }}
        >
          {loading ? "Saving..." : "Log Workout"}
        </button>
        {logResult && (
          <div style={{ marginTop: 15, padding: 10, background: "#f0f0f0" }}>
            <strong>Saved:</strong> {logResult}
          </div>
        )}
      </section>

      <section>
        <h2>Ask Your Coach</h2>
        <input
          style={{ width: "100%", padding: 10, fontSize: 14 }}
          placeholder="e.g. How has my running improved this week?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          onClick={askQuestion}
          disabled={loading || !question}
          style={{ marginTop: 10, padding: "10px 20px", cursor: "pointer" }}
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
        {answer && (
          <div style={{ marginTop: 15, padding: 10, background: "#f0f0f0" }}>
            <strong>Coach:</strong> {answer}
          </div>
        )}
      </section>
    </div>
  );
}

export default App;