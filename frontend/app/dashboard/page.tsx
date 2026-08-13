"use client";

import { useEffect, useState } from "react";

type Analytics = {
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
};

export default function Dashboard() {
  const [analytics, setAnalytics] = useState<Analytics>({
    total_calls: 0,
    successful_calls: 0,
    failed_calls: 0,
  });

  async function loadAnalytics() {
    const response = await fetch("http://127.0.0.1:8001/analytics");

    if (!response.ok) {
      throw new Error("Failed to load analytics");
    }

    const data = await response.json();
    setAnalytics(data);
  }

  useEffect(() => {
    loadAnalytics();

    const interval = setInterval(loadAnalytics, 3000);

    return () => clearInterval(interval);
  }, []);

  const successRate =
    analytics.total_calls > 0
      ? Math.round(
          (analytics.successful_calls / analytics.total_calls) * 100
        )
      : 0;

  const failureRate =
    analytics.total_calls > 0
      ? Math.round(
          (analytics.failed_calls / analytics.total_calls) * 100
        )
      : 0;

  return (
    <main
      style={{
        minHeight: "100vh",
        background:
          "linear-gradient(135deg, #0f172a 0%, #111827 50%, #020617 100%)",
        color: "#f8fafc",
        padding: "40px",
        fontFamily:
          "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
        }}
      >
        {/* Header */}
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "45px",
          }}
        >
          <div>
            <div
              style={{
                color: "#818cf8",
                fontSize: "14px",
                fontWeight: 700,
                letterSpacing: "1.5px",
                textTransform: "uppercase",
                marginBottom: "8px",
              }}
            >
              TechFlow
            </div>

            <h1
              style={{
                fontSize: "36px",
                margin: 0,
                fontWeight: 800,
                letterSpacing: "-1px",
              }}
            >
              Call Analytics
            </h1>

            <p
              style={{
                marginTop: "10px",
                color: "#94a3b8",
                fontSize: "15px",
              }}
            >
              Real-time voice agent performance overview
            </p>
          </div>

          {/* Live status */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "9px",
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.25)",
              padding: "10px 16px",
              borderRadius: "999px",
              color: "#6ee7b7",
              fontSize: "14px",
              fontWeight: 600,
            }}
          >
            <span
              style={{
                width: "9px",
                height: "9px",
                borderRadius: "50%",
                background: "#10b981",
                boxShadow: "0 0 12px rgba(16, 185, 129, 0.8)",
              }}
            />

            Live
          </div>
        </header>

        {/* Stats */}
        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "20px",
            marginBottom: "25px",
          }}
        >
          {/* Total */}
          <div
            style={{
              background: "rgba(30, 41, 59, 0.72)",
              border: "1px solid rgba(148, 163, 184, 0.12)",
              borderRadius: "20px",
              padding: "28px",
              boxShadow: "0 15px 40px rgba(0, 0, 0, 0.2)",
            }}
          >
            <div
              style={{
                color: "#94a3b8",
                fontSize: "14px",
                fontWeight: 600,
                marginBottom: "18px",
              }}
            >
              TOTAL CALLS
            </div>

            <div
              style={{
                fontSize: "42px",
                fontWeight: 800,
              }}
            >
              {analytics.total_calls}
            </div>

            <div
              style={{
                marginTop: "10px",
                color: "#64748b",
                fontSize: "13px",
              }}
            >
              All processed calls
            </div>
          </div>

          {/* Successful */}
          <div
            style={{
              background:
                "linear-gradient(145deg, rgba(16,185,129,0.14), rgba(30,41,59,0.72))",
              border: "1px solid rgba(16, 185, 129, 0.2)",
              borderRadius: "20px",
              padding: "28px",
              boxShadow: "0 15px 40px rgba(0, 0, 0, 0.2)",
            }}
          >
            <div
              style={{
                color: "#6ee7b7",
                fontSize: "14px",
                fontWeight: 600,
                marginBottom: "18px",
              }}
            >
              SUCCESSFUL CALLS
            </div>

            <div
              style={{
                fontSize: "42px",
                fontWeight: 800,
              }}
            >
              {analytics.successful_calls}
            </div>

            <div
              style={{
                marginTop: "10px",
                color: "#94a3b8",
                fontSize: "13px",
              }}
            >
              {successRate}% success rate
            </div>
          </div>

          {/* Failed */}
          <div
            style={{
              background:
                "linear-gradient(145deg, rgba(239,68,68,0.12), rgba(30,41,59,0.72))",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              borderRadius: "20px",
              padding: "28px",
              boxShadow: "0 15px 40px rgba(0, 0, 0, 0.2)",
            }}
          >
            <div
              style={{
                color: "#fca5a5",
                fontSize: "14px",
                fontWeight: 600,
                marginBottom: "18px",
              }}
            >
              FAILED CALLS
            </div>

            <div
              style={{
                fontSize: "42px",
                fontWeight: 800,
              }}
            >
              {analytics.failed_calls}
            </div>

            <div
              style={{
                marginTop: "10px",
                color: "#94a3b8",
                fontSize: "13px",
              }}
            >
              {failureRate}% failure rate
            </div>
          </div>
        </section>

        {/* Performance panel */}
        <section
          style={{
            background: "rgba(30, 41, 59, 0.72)",
            border: "1px solid rgba(148, 163, 184, 0.12)",
            borderRadius: "20px",
            padding: "30px",
            boxShadow: "0 15px 40px rgba(0, 0, 0, 0.2)",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "25px",
            }}
          >
            <div>
              <h2
                style={{
                  margin: 0,
                  fontSize: "20px",
                  fontWeight: 700,
                }}
              >
                Overall Performance
              </h2>

              <p
                style={{
                  margin: "7px 0 0",
                  color: "#64748b",
                  fontSize: "13px",
                }}
              >
                Current call completion performance
              </p>
            </div>

            <div
              style={{
                fontSize: "30px",
                fontWeight: 800,
                color: "#a5b4fc",
              }}
            >
              {successRate}%
            </div>
          </div>

          {/* Progress */}
          <div
            style={{
              width: "100%",
              height: "12px",
              background: "#0f172a",
              borderRadius: "999px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${successRate}%`,
                height: "100%",
                background:
                  "linear-gradient(90deg, #6366f1, #8b5cf6)",
                borderRadius: "999px",
                transition: "width 0.5s ease",
              }}
            />
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginTop: "14px",
              color: "#64748b",
              fontSize: "13px",
            }}
          >
            <span>Successful</span>
            <span>{successRate}%</span>
          </div>
        </section>

        {/* Footer */}
        <div
          style={{
            textAlign: "center",
            marginTop: "30px",
            color: "#475569",
            fontSize: "12px",
          }}
        >
          Analytics refresh automatically every 3 seconds
        </div>
      </div>
    </main>
  );
}
