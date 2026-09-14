'use client';

import React from 'react';
import { Stethoscope, LogOut, Database, User } from 'lucide-react';
import { User as UserType } from '../types';

interface HeaderProps {
  user: UserType;
  onLogout: () => void;
  onOpenCollections: () => void;
}

const roleBadgeColors: Record<string, { bg: string; text: string; border: string }> = {
  doctor: { bg: 'bg-emerald-900/30', text: 'text-emerald-300', border: 'border-emerald-700/40' },
  nurse: { bg: 'bg-lime-900/30', text: 'text-lime-300', border: 'border-lime-700/40' },
  billing_executive: { bg: 'bg-amber-900/30', text: 'text-amber-300', border: 'border-amber-700/40' },
  technician: { bg: 'bg-stone-800/50', text: 'text-stone-300', border: 'border-stone-600/40' },
  admin: { bg: 'bg-orange-900/30', text: 'text-orange-300', border: 'border-orange-700/40' },
};

export default function Header({ user, onLogout, onOpenCollections }: HeaderProps) {
  const badgeStyle = roleBadgeColors[user.role] || roleBadgeColors.nurse;

  return (
    <header className="glass-panel sticky top-0 z-30 px-4 md:px-8 py-3.5 border-b border-stone-800 flex items-center justify-between">
      {/* Left: Branding */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-900/20 border border-amber-700/30 flex items-center justify-center shadow-inner">
          <Stethoscope className="w-5 h-5 text-amber-500" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-stone-100 tracking-tight">MediBot</h1>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/30 text-amber-300 font-semibold uppercase border border-amber-700/30">RAG 2.0</span>
          </div>
          <p className="text-xs text-stone-400 hidden sm:block">MediAssist Internal Clinical Assistant</p>
        </div>
      </div>

      {/* Right: User Profile & Actions */}
      <div className="flex items-center gap-3">
        {/* Collections Access Matrix Button */}
        <button
          onClick={onOpenCollections}
          className="px-3 py-1.5 rounded-lg bg-stone-800/80 hover:bg-stone-700/80 border border-stone-700/50 text-xs text-stone-300 hover:text-stone-100 flex items-center gap-1.5 transition-colors cursor-pointer"
          title="View Accessible Collections"
        >
          <Database className="w-3.5 h-3.5 text-amber-400" />
          <span className="hidden md:inline">Permissions</span>
        </button>

        {/* Role Badge & Profile */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-stone-900/70 border border-stone-800">
          <div className="w-7 h-7 rounded-full bg-stone-800 border border-stone-700 flex items-center justify-center text-stone-300">
            <User className="w-4 h-4" />
          </div>
          <div className="text-left hidden sm:block">
            <p className="text-xs font-semibold text-stone-100 leading-tight">{user.full_name}</p>
            <span className={`text-[10px] font-bold uppercase tracking-wider ${badgeStyle.text}`}>
              {user.role.replace('_', ' ')}
            </span>
          </div>
          <span className={`sm:hidden text-[10px] uppercase font-bold px-2 py-0.5 rounded ${badgeStyle.bg} ${badgeStyle.text} border ${badgeStyle.border}`}>
            {user.role.replace('_', ' ')}
          </span>
        </div>

        {/* Logout Button */}
        <button
          onClick={onLogout}
          className="p-2 rounded-lg bg-orange-950/40 hover:bg-orange-900/40 border border-orange-800/40 text-orange-400 hover:text-orange-300 transition-colors cursor-pointer"
          title="Logout"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
