import { DemoAccount } from '../types';

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    username: 'dr.mehta',
    password: 'doctor123',
    full_name: 'Dr. Rajesh Mehta',
    role: 'doctor',
    department: 'Clinical Cardiology',
    accessible_collections: ['general', 'clinical', 'nursing'],
  },
  {
    username: 'nurse.priya',
    password: 'nurse123',
    full_name: 'Nurse Priya Sharma',
    role: 'nurse',
    department: 'ICU Nursing Care',
    accessible_collections: ['general', 'nursing'],
  },
  {
    username: 'billing.ravi',
    password: 'billing123',
    full_name: 'Ravi Kumar',
    role: 'billing_executive',
    department: 'Billing & Claims',
    accessible_collections: ['general', 'billing'],
  },
  {
    username: 'tech.anand',
    password: 'tech123',
    full_name: 'Anand Verma',
    role: 'technician',
    department: 'Equipment Maintenance',
    accessible_collections: ['general', 'equipment'],
  },
  {
    username: 'admin.sys',
    password: 'admin123',
    full_name: 'System Administrator',
    role: 'admin',
    department: 'Executive IT Admin',
    accessible_collections: ['general', 'clinical', 'nursing', 'billing', 'equipment'],
  },
];
