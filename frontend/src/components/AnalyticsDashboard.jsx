import React, { useEffect, useState } from "react";
import { MessageSquare, DollarSign, Zap, Shield, RotateCw, Activity, HeartHandshake, TrendingUp, BarChart2, PieChart } from "lucide-react";
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement } from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement);

export default function AnalyticsDashboard() {
  const [summary, setSummary] = useState({});
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAnalytics = async () => {
    setLoading(true);
    try {
      const [sumRes, logsRes] = await Promise.all([
        fetch("/api/v1/analytics/summary"),
        fetch("/api/v1/analytics/logs?limit=20")
      ]);
      const sumData = await sumRes.json();
      const logsData = await logsRes.json();
      setSummary(sumData);
      setLogs(logsData);
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const reversedLogs = [...logs].reverse();
  const queryLabels = reversedLogs.map((l) => "Q#" + l.id);

  // Chart 1: Latency per Query
  const latencyChartData = {
    labels: queryLabels,
    datasets: [
      {
        label: "Response Speed (sec)",
        data: reversedLogs.map((l) => l.latency_seconds || 0),
        backgroundColor: "rgba(0, 242, 254, 0.5)",
        borderColor: "#00f2fe",
        borderWidth: 1
      }
    ]
  };

  // Chart 2: Quality & Verification Breakdown
  const accuracyData = {
    labels: ["Source Relevance", "Fact Accuracy", "Response Usefulness"],
    datasets: [
      {
        data: [
          summary.document_relevance_rate_pct || 100,
          summary.groundedness_accuracy_rate_pct || 100,
          summary.usefulness_rate_pct || 100
        ],
        backgroundColor: ["#00f2fe", "#00e676", "#7f00ff"]
      }
    ]
  };

  // Chart 3: Cost Trend per Query ($ USD)
  const costChartData = {
    labels: queryLabels,
    datasets: [
      {
        label: "Estimated Cost ($ USD)",
        data: reversedLogs.map((l) => l.estimated_cost_usd || 0),
        borderColor: "#00e676",
        backgroundColor: "rgba(0, 230, 118, 0.2)",
        fill: true,
        tension: 0.35,
        borderWidth: 2,
        pointBackgroundColor: "#00e676"
      }
    ]
  };

  // Chart 4: Token Consumption Distribution (Prompt vs Completion)
  const tokenChartData = {
    labels: queryLabels,
    datasets: [
      {
        label: "Total Tokens",
        data: reversedLogs.map((l) => l.total_tokens || 0),
        backgroundColor: "rgba(127, 0, 255, 0.6)",
        borderColor: "#7f00ff",
        borderWidth: 1
      }
    ]
  };

  // Chart 5: User Feedback & Satisfaction
  const positiveCount = summary.positive_feedback_count || 0;
  const negativeCount = summary.negative_feedback_count || 0;
  const unratedCount = Math.max(0, (summary.total_queries || 0) - (positiveCount + negativeCount));

  const feedbackChartData = {
    labels: ["Positive (👍)", "Negative (👎)", "Unrated"],
    datasets: [
      {
        data: [
          positiveCount > 0 || negativeCount > 0 ? positiveCount : 1,
          negativeCount,
          positiveCount === 0 && negativeCount === 0 ? 0 : unratedCount
        ],
        backgroundColor: ["#00e676", "#ff5252", "rgba(255, 255, 255, 0.15)"]
      }
    ]
  };

  return (
    <div className="analytics-dashboard">
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-icon blue"><MessageSquare /></div>
          <div className="metric-body">
            <span className="metric-label">Questions Answered</span>
            <h3>{summary.total_queries || 0}</h3>
            <span className="metric-sub">{summary.total_sessions || 0} User Sessions</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon green"><DollarSign /></div>
          <div className="metric-body">
            <span className="metric-label">Total API Cost ($ USD)</span>
            <h3>${(summary.total_cost_usd || 0).toFixed(6)}</h3>
            <span className="metric-sub">Avg ${(summary.avg_cost_per_query_usd || 0).toFixed(6)}/query</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon purple"><Zap /></div>
          <div className="metric-body">
            <span className="metric-label">Avg Response Speed</span>
            <h3>{(summary.avg_latency_seconds || 0).toFixed(1)}s</h3>
            <span className="metric-sub">{(summary.total_tokens || 0).toLocaleString()} Total Tokens</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon orange"><Shield /></div>
          <div className="metric-body">
            <span className="metric-label">Clinical Accuracy Rate</span>
            <h3>{summary.groundedness_accuracy_rate_pct || 0}%</h3>
            <span className="metric-sub">{summary.document_relevance_rate_pct || 0}% Source Match</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon green"><HeartHandshake /></div>
          <div className="metric-body">
            <span className="metric-label">User Satisfaction</span>
            <h3>{summary.user_satisfaction_rate_pct || 100}%</h3>
            <span className="metric-sub">{summary.positive_feedback_count || 0} 👍 / {summary.negative_feedback_count || 0} 👎</span>
          </div>
        </div>
      </div>

      {/* Row 1: Speed, Quality, Cost */}
      <div className="charts-row" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <div className="chart-card glass">
          <div className="chart-header">
            <h3><Activity size={18} color="#00f2fe" style={{ marginRight: "8px" }} /> 1. Response Speed per Query (sec)</h3>
          </div>
          <div className="chart-container">
            <Bar data={latencyChartData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>

        <div className="chart-card glass">
          <div className="chart-header">
            <h3><Shield size={18} color="#00e676" style={{ marginRight: "8px" }} /> 2. Quality & Verification Breakdown</h3>
          </div>
          <div className="chart-container">
            <Doughnut data={accuracyData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>

        <div className="chart-card glass">
          <div className="chart-header">
            <h3><TrendingUp size={18} color="#00e676" style={{ marginRight: "8px" }} /> 3. Estimated Cost Trend ($ USD)</h3>
          </div>
          <div className="chart-container">
            <Line data={costChartData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>
      </div>

      {/* Row 2: Tokens, User Feedback */}
      <div className="charts-row" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", marginTop: "16px" }}>
        <div className="chart-card glass">
          <div className="chart-header">
            <h3><BarChart2 size={18} color="#7f00ff" style={{ marginRight: "8px" }} /> 4. Token Consumption per Query</h3>
          </div>
          <div className="chart-container">
            <Bar data={tokenChartData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>

        <div className="chart-card glass">
          <div className="chart-header">
            <h3><PieChart size={18} color="#ff5252" style={{ marginRight: "8px" }} /> 5. User Feedback & Satisfaction</h3>
          </div>
          <div className="chart-container">
            <Doughnut data={feedbackChartData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="logs-table-card glass" style={{ marginTop: "24px" }}>
        <div className="table-header">
          <h3>Medical Audit Log History</h3>
          <button className="btn-primary" onClick={fetchAnalytics} style={{ padding: "6px 16px", fontSize: "12px" }}>
            <RotateCw size={14} /> Refresh Logs
          </button>
        </div>
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Session</th>
                <th>User Question</th>
                <th>Search Query</th>
                <th>Relevant</th>
                <th>Accurate</th>
                <th>Helpful</th>
                <th>Feedback</th>
                <th>Speed</th>
                <th>Tokens</th>
                <th>Cost ($)</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td>#{l.id}</td>
                  <td><code>{l.session_id}</code></td>
                  <td>{l.question.substring(0, 30)}...</td>
                  <td><em>{l.generated_query || "-"}</em></td>
                  <td><span className={`badge ${l.is_relevant}`}>{l.is_relevant}</span></td>
                  <td><span className={`badge ${l.is_grounded}`}>{l.is_grounded}</span></td>
                  <td><span className={`badge ${l.is_useful}`}>{l.is_useful}</span></td>
                  <td>
                    {l.user_feedback === "positive" && <span style={{ color: "#00e676", fontWeight: "bold" }}>👍 Helpful</span>}
                    {l.user_feedback === "negative" && <span style={{ color: "#ff5252", fontWeight: "bold" }}>👎 Inaccurate</span>}
                    {!l.user_feedback && <span style={{ color: "var(--text-muted)" }}>-</span>}
                  </td>
                  <td>{l.latency_seconds ? l.latency_seconds + "s" : "-"}</td>
                  <td>{l.total_tokens}</td>
                  <td>${l.estimated_cost_usd}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
