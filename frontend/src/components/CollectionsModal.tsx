'use client';

import React from 'react';
import { ShieldCheck, X, Database, Lock, Unlock } from 'lucide-react';
import { User as UserType } from '../types';

interface CollectionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  user: UserType;
  accessibleCollections: string[];
}

const ALL_COLLECTIONS_INFO = [
  { name: 'general', title: 'Hospital HR & Staff Handbooks', desc: 'Hospital HR policy, leave guidelines, FAQs, code of conduct' },
  { name: 'clinical', title: 'Clinical Guidelines & Formularies', desc: 'Treatment protocols, drug formulary reference, diagnostic criteria' },
  { name: 'nursing', title: 'Nursing Procedures & ICU Care', desc: 'ICU nursing procedures, infection control guidelines, cannula sizing' },
  { name: 'billing', title: 'Insurance Billing & Claim Guides', desc: 'ICD-10 insurance billing codes, claim submission procedures' },
  { name: 'equipment', title: 'Medical Equipment & Calibration', desc: 'Equipment operation manuals, calibration schedules, maintenance' },
];

export default function CollectionsModal({
  isOpen,
  onClose,
  user,
  accessibleCollections,
}: CollectionsModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="glass-panel w-full max-w-xl rounded-2xl border border-stone-700/60 p-6 space-y-6 shadow-2xl relative">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg bg-stone-800 hover:bg-stone-700 text-stone-400 hover:text-stone-100 transition-colors cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="flex items-center gap-3 border-b border-stone-800 pb-4">
          <div className="w-10 h-10 rounded-xl bg-amber-900/20 border border-amber-700/30 flex items-center justify-center">
            <Database className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-stone-100 flex items-center gap-2">
              Role Access Permissions Matrix
            </h3>
            <p className="text-xs text-stone-400">
              Vector DB metadata filters enforced for role: <span className="text-amber-300 font-semibold uppercase">{user.role}</span>
            </p>
          </div>
        </div>

        {/* Collections List */}
        <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
          {ALL_COLLECTIONS_INFO.map((col) => {
            const isAccessible = accessibleCollections.includes(col.name);

            return (
              <div
                key={col.name}
                className={`p-3.5 rounded-xl border flex items-start justify-between gap-3 transition-all ${
                  isAccessible
                    ? 'bg-lime-950/20 border-lime-700/30'
                    : 'bg-stone-900/40 border-stone-800 opacity-60'
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-stone-100 capitalize">{col.name}</span>
                    <span className="text-[10px] text-stone-400">Collection</span>
                  </div>
                  <p className="text-xs font-medium text-stone-300">{col.title}</p>
                  <p className="text-[11px] text-stone-400">{col.desc}</p>
                </div>

                <div className="shrink-0 pt-0.5">
                  {isAccessible ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-bold text-lime-300 bg-lime-950/40 px-2.5 py-1 rounded-md border border-lime-700/40">
                      <Unlock className="w-3 h-3" /> Granted
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-bold text-orange-400 bg-orange-950/40 px-2.5 py-1 rounded-md border border-orange-800/40">
                      <Lock className="w-3 h-3" /> Blocked (RBAC)
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Security Footer Note */}
        <div className="p-3 rounded-xl bg-stone-900/80 border border-stone-800 text-[11px] text-stone-400 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            Qdrant evaluates <code className="text-amber-300">access_roles</code> metadata filters at vector retrieval index level. Adversarial prompts cannot bypass blocked collections.
          </span>
        </div>
      </div>
    </div>
  );
}
