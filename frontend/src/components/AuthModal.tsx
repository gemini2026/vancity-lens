"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function AuthModal({ isOpen, onClose }: AuthModalProps) {
  const { login, signup } = useAuth();
  const [tab, setTab] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        await signup(email, password, displayName || undefined);
      }
      onClose();
      setEmail("");
      setPassword("");
      setDisplayName("");
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    background: "#1e293b",
    border: "1px solid #374151",
    borderRadius: "6px",
    color: "#f3f4f6",
    fontSize: "13px",
    fontFamily: "inherit",
    boxSizing: "border-box",
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        backdropFilter: "blur(4px)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#111827",
          border: "1px solid #1f2937",
          borderRadius: "12px",
          width: "100%",
          maxWidth: "400px",
          padding: "32px",
          fontFamily: "system-ui, sans-serif",
          color: "#f3f4f6",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "24px" }}>
          <div style={{ fontSize: "20px", fontWeight: 700 }}>VanCity Lens</div>
          <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "4px" }}>
            {tab === "login" ? "Sign in to your account" : "Create your account"}
          </div>
        </div>

        {/* Tabs */}
        <div
          style={{
            display: "flex",
            marginBottom: "20px",
            borderRadius: "6px",
            overflow: "hidden",
            border: "1px solid #374151",
          }}
        >
          {(["login", "signup"] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setError(""); }}
              style={{
                flex: 1,
                padding: "8px",
                background: tab === t ? "#1e293b" : "transparent",
                border: "none",
                color: tab === t ? "#f3f4f6" : "#6b7280",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {t === "login" ? "Log In" : "Sign Up"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {tab === "signup" && (
              <input
                type="text"
                placeholder="Display name (optional)"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                style={inputStyle}
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              style={inputStyle}
            />
          </div>

          {error && (
            <div
              style={{
                marginTop: "12px",
                padding: "8px 12px",
                background: "rgba(220,38,38,0.1)",
                border: "1px solid rgba(220,38,38,0.3)",
                borderRadius: "6px",
                color: "#fca5a5",
                fontSize: "12px",
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              marginTop: "16px",
              padding: "10px",
              background: loading ? "#4b5563" : "#3b82f6",
              border: "none",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "13px",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Please wait..." : tab === "login" ? "Log In" : "Create Account"}
          </button>
        </form>

        <button
          onClick={onClose}
          style={{
            display: "block",
            margin: "16px auto 0",
            background: "none",
            border: "none",
            color: "#6b7280",
            fontSize: "12px",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
