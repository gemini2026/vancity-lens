"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
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
      <div className="p-12 text-center text-gray-500">
        <div className="text-[32px] mb-3">&#127970;</div>
        <div className="text-sm">Sign in to manage organizations</div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-[800px] mx-auto text-gray-100">
      <h2 className="text-lg font-bold mb-5">Organization Settings</h2>

      {/* Create org */}
      <div className="p-4 bg-slate-800 rounded-lg border border-gray-700 mb-5">
        <div className="text-[13px] font-semibold mb-2">Create Organization</div>
        <div className="flex gap-2">
          <input
            value={newOrgName}
            onChange={(e) => setNewOrgName(e.target.value)}
            placeholder="Organization name"
            className="flex-1 px-3 py-2 bg-slate-900 border border-gray-700 rounded-md text-gray-100 text-[13px]"
          />
          <button
            onClick={handleCreateOrg}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 border-none rounded-md text-white text-[13px] font-semibold cursor-pointer"
          >
            Create
          </button>
        </div>
      </div>

      {/* Org list */}
      {orgs.length > 0 && (
        <div className="mb-5">
          <div className="text-[13px] font-semibold text-gray-400 mb-2">
            Your Organizations
          </div>
          {orgs.map((org) => (
            <div
              key={org.id}
              onClick={() => {
                setSelectedOrg(org);
                loadMembers(org.id);
              }}
              className={cn(
                "px-4 py-3 rounded-lg cursor-pointer mb-2 flex justify-between items-center",
                selectedOrg?.id === org.id
                  ? "bg-blue-500/[0.12] border border-blue-500"
                  : "bg-slate-800 border border-gray-700"
              )}
            >
              <div>
                <div className="text-sm font-semibold">{org.name}</div>
                <div className="text-[11px] text-gray-500">
                  {org.plan} · {org.max_seats} seats
                </div>
              </div>
              <span className="text-[10px] text-gray-500 bg-gray-700 px-1.5 py-0.5 rounded-sm">
                {(org as any).role || "owner"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Members for selected org */}
      {selectedOrg && (
        <div className="p-4 bg-slate-800 rounded-lg border border-gray-700">
          <div className="text-[13px] font-semibold mb-3">
            {selectedOrg.name} — Members
          </div>

          {/* Invite */}
          <div className="flex gap-2 mb-4">
            <input
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="Email address"
              className="flex-1 px-3 py-2 bg-slate-900 border border-gray-700 rounded-md text-gray-100 text-xs"
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="px-2 py-2 bg-slate-900 border border-gray-700 rounded-md text-gray-300 text-xs"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button
              onClick={handleInvite}
              disabled={loading}
              className="px-3 py-2 bg-blue-500 border-none rounded-md text-white text-xs font-semibold cursor-pointer"
            >
              Invite
            </button>
          </div>

          {/* Member list */}
          {members.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between py-2 border-b border-gray-700"
            >
              <div>
                <div className="text-[13px] text-gray-300">
                  {m.full_name || m.email}
                </div>
                <div className="text-[10px] text-gray-500">{m.email}</div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded-sm text-white font-semibold",
                    m.role === "owner"
                      ? "bg-amber-500"
                      : m.role === "admin"
                        ? "bg-blue-500"
                        : "bg-gray-700"
                  )}
                >
                  {m.role}
                </span>
                {m.role !== "owner" && (
                  <button
                    onClick={() => handleRemove(m.user_id)}
                    className="bg-transparent border-none text-gray-500 cursor-pointer text-[11px]"
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
