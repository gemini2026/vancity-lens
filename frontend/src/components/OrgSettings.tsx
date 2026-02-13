"use client";

import { useState, useEffect } from "react";
import { getApiBase } from "@/lib/api-base";

const API_BASE = getApiBase();

interface OrgMember {
  id: number;
  user_id: number;
  email: string;
  full_name: string | null;
  role: string;
  joined_at: string;
}

interface Org {
  id: number;
  name: string;
  slug: string;
  plan: string;
  max_seats: number;
}

export default function OrgSettings({ token }: { token?: string }) {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Org | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [newOrgName, setNewOrgName] = useState("");
  const [loading, setLoading] = useState(false);

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/api/v1/orgs`, { headers })
      .then((r) => r.json())
      .then(setOrgs)
      .catch(() => {});
  }, [token]);

  const loadMembers = async (orgId: number) => {
    const res = await fetch(`${API_BASE}/api/v1/orgs/${orgId}/members`, { headers });
    if (res.ok) setMembers(await res.json());
  };

  const handleCreateOrg = async () => {
    if (!newOrgName.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/orgs`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: newOrgName.trim() }),
      });
      if (res.ok) {
        const org = await res.json();
        setOrgs((prev) => [...prev, org]);
        setNewOrgName("");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleInvite = async () => {
    if (!selectedOrg || !inviteEmail.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/orgs/${selectedOrg.id}/members`, {
        method: "POST",
        headers,
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      });
      if (res.ok) {
        await loadMembers(selectedOrg.id);
        setInviteEmail("");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (userId: number) => {
    if (!selectedOrg) return;
    await fetch(`${API_BASE}/api/v1/orgs/${selectedOrg.id}/members/${userId}`, {
      method: "DELETE",
      headers,
    });
    await loadMembers(selectedOrg.id);
  };

  if (!token) {
    return (
      <div style={{ padding: "48px", textAlign: "center", color: "#6b7280" }}>
        <div style={{ fontSize: "32px", marginBottom: "12px" }}>🏢</div>
        <div style={{ fontSize: "14px" }}>Sign in to manage organizations</div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "24px",
        maxWidth: "800px",
        margin: "0 auto",
        fontFamily: "system-ui, sans-serif",
        color: "#f3f4f6",
      }}
    >
      <h2 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "20px" }}>
        Organization Settings
      </h2>

      {/* Create org */}
      <div
        style={{
          padding: "16px",
          background: "#1e293b",
          borderRadius: "8px",
          border: "1px solid #374151",
          marginBottom: "20px",
        }}
      >
        <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "8px" }}>
          Create Organization
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            value={newOrgName}
            onChange={(e) => setNewOrgName(e.target.value)}
            placeholder="Organization name"
            style={{
              flex: 1,
              padding: "8px 12px",
              background: "#0f172a",
              border: "1px solid #374151",
              borderRadius: "6px",
              color: "#f3f4f6",
              fontSize: "13px",
            }}
          />
          <button
            onClick={handleCreateOrg}
            disabled={loading}
            style={{
              padding: "8px 16px",
              background: "#3b82f6",
              border: "none",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Create
          </button>
        </div>
      </div>

      {/* Org list */}
      {orgs.length > 0 && (
        <div style={{ marginBottom: "20px" }}>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#9ca3af", marginBottom: "8px" }}>
            Your Organizations
          </div>
          {orgs.map((org) => (
            <div
              key={org.id}
              onClick={() => {
                setSelectedOrg(org);
                loadMembers(org.id);
              }}
              style={{
                padding: "12px 16px",
                background: selectedOrg?.id === org.id ? "rgba(59,130,246,0.12)" : "#1e293b",
                border: selectedOrg?.id === org.id ? "1px solid #3b82f6" : "1px solid #374151",
                borderRadius: "8px",
                cursor: "pointer",
                marginBottom: "8px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div style={{ fontSize: "14px", fontWeight: 600 }}>{org.name}</div>
                <div style={{ fontSize: "11px", color: "#6b7280" }}>
                  {org.plan} · {org.max_seats} seats
                </div>
              </div>
              <span style={{ fontSize: "10px", color: "#6b7280", background: "#374151", padding: "2px 6px", borderRadius: "3px" }}>
                {(org as any).role || "owner"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Members for selected org */}
      {selectedOrg && (
        <div
          style={{
            padding: "16px",
            background: "#1e293b",
            borderRadius: "8px",
            border: "1px solid #374151",
          }}
        >
          <div style={{ fontSize: "13px", fontWeight: 600, marginBottom: "12px" }}>
            {selectedOrg.name} — Members
          </div>

          {/* Invite */}
          <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
            <input
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="Email address"
              style={{
                flex: 1,
                padding: "8px 12px",
                background: "#0f172a",
                border: "1px solid #374151",
                borderRadius: "6px",
                color: "#f3f4f6",
                fontSize: "12px",
              }}
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              style={{
                padding: "8px",
                background: "#0f172a",
                border: "1px solid #374151",
                borderRadius: "6px",
                color: "#d1d5db",
                fontSize: "12px",
              }}
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button
              onClick={handleInvite}
              disabled={loading}
              style={{
                padding: "8px 12px",
                background: "#3b82f6",
                border: "none",
                borderRadius: "6px",
                color: "#fff",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Invite
            </button>
          </div>

          {/* Member list */}
          {members.map((m) => (
            <div
              key={m.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 0",
                borderBottom: "1px solid #374151",
              }}
            >
              <div>
                <div style={{ fontSize: "13px", color: "#d1d5db" }}>
                  {m.full_name || m.email}
                </div>
                <div style={{ fontSize: "10px", color: "#6b7280" }}>{m.email}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span
                  style={{
                    fontSize: "10px",
                    padding: "2px 6px",
                    borderRadius: "3px",
                    background: m.role === "owner" ? "#f59e0b" : m.role === "admin" ? "#3b82f6" : "#374151",
                    color: "#fff",
                    fontWeight: 600,
                  }}
                >
                  {m.role}
                </span>
                {m.role !== "owner" && (
                  <button
                    onClick={() => handleRemove(m.user_id)}
                    style={{
                      background: "none",
                      border: "none",
                      color: "#6b7280",
                      cursor: "pointer",
                      fontSize: "11px",
                    }}
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
