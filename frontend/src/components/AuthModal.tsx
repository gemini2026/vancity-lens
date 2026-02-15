"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const inputClasses =
  "w-full px-3 py-2.5 bg-slate-800 border border-gray-700 rounded-md text-gray-100 text-[13px] font-[inherit] box-border";

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

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-[1000] backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-gray-900 border border-gray-800 rounded-xl w-full max-w-[400px] p-8 text-gray-100"
      >
        <div className="text-center mb-6">
          <div className="text-xl font-bold">VanCity Lens</div>
          <div className="text-xs text-gray-500 mt-1">
            {tab === "login" ? "Sign in to your account" : "Create your account"}
          </div>
        </div>

        <div className="flex mb-5 rounded-md overflow-hidden border border-gray-700">
          {(["login", "signup"] as const).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); setError(""); }}
              className={cn(
                "flex-1 p-2 border-none text-xs font-semibold cursor-pointer",
                tab === t
                  ? "bg-slate-800 text-gray-100"
                  : "bg-transparent text-gray-500"
              )}
            >
              {t === "login" ? "Log In" : "Sign Up"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="flex flex-col gap-3">
            {tab === "signup" && (
              <input
                type="text"
                placeholder="Display name (optional)"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className={inputClasses}
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className={inputClasses}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className={inputClasses}
            />
          </div>

          {error && (
            <div className="mt-3 px-3 py-2 bg-red-700/10 border border-red-700/30 rounded-md text-red-300 text-xs">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className={cn(
              "w-full mt-4 py-2.5 border-none rounded-md text-white text-[13px] font-semibold",
              loading
                ? "bg-gray-600 cursor-not-allowed"
                : "bg-blue-500 cursor-pointer hover:bg-blue-600"
            )}
          >
            {loading ? "Please wait..." : tab === "login" ? "Log In" : "Create Account"}
          </button>
        </form>

        <button
          onClick={onClose}
          className="block mx-auto mt-4 bg-none border-none text-gray-500 text-xs cursor-pointer hover:text-gray-300"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
