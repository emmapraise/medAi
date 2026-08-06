import React, { useEffect, useState } from "react";
import { MessageSquare, DollarSign, Zap, Shield, RotateCw, Activity } from "lucide-react";
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement } from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";

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
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, []);

  const latencyChartData = {
    labels: [...logs].reverse().map((l) => "Query #" + l.id),
    datasets: [
      {
        label: "Response Speed (sec)",
        data: [...logs].reverse().map((l) => l.latency_seconds),
        backgroundColor: "rgba(0, 242, 254, 0.5)",
        borderColor: "#00f2fe",
        borderWidth: 1
      }
    ]
  };

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
            <span className="metric-sub">Avg ${(summary.avg_cost_per_query_usd || 0).toFixed(6)}/question</span>
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
      </div>

      <div className="charts-row">
        <div className="chart-card glass">
          <div className="chart-header">
            <h3><Activity size={18} color="#00f2fe" style={{ marginRight: "8px" }} /> Response Speed per Query (sec)</h3>
          </div>
          <div className="chart-container">
            <Bar data={latencyChartData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>

        <div className="chart-card glass">
          <div className="chart-header">
            <h3>Quality & Verification Breakdown</h3>
          </div>
          <div className="chart-container">
            <Doughnut data={accuracyData} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </div>
      </div>

      <div className="logs-table-card glass">
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
                  <td>{l.question.substring(0, 32)}...</td>
                  <td><em>{l.generated_query || "-"}</em></td>
                  <td><span className={`badge ${l.is_relevant}`}>{l.is_relevant}</span></td>
                  <td><span className={`badge ${l.is_grounded}`}>{l.is_grounded}</span></td>
                  <td><span className={`badge ${l.is_useful}`}>{l.is_useful}</span></td>
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
