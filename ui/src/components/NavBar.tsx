import { NavLink, useNavigate } from "react-router-dom";
import { LogOut, ShieldCheck } from "lucide-react";
import { clearKey } from "../lib/auth";

interface NavBarProps {
  isAdmin: boolean;
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded text-sm font-medium transition-colors ${
    isActive ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"
  }`;

export function NavBar({ isAdmin }: NavBarProps) {
  const navigate = useNavigate();

  function handleLogout() {
    clearKey();
    navigate("/login");
  }

  return (
    <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center gap-2">
      <ShieldCheck className="text-indigo-400 mr-2" size={20} />
      <span className="font-semibold text-white mr-6">pii-protect</span>
      <NavLink to="/dashboard" className={linkClass}>Dashboard</NavLink>
      {isAdmin && <NavLink to="/api-keys" className={linkClass}>API Keys</NavLink>}
      {isAdmin && <NavLink to="/regex-patterns" className={linkClass}>Regex</NavLink>}
      {isAdmin && <NavLink to="/denylist" className={linkClass}>Denylist</NavLink>}
      {isAdmin && <NavLink to="/context-words" className={linkClass}>Context</NavLink>}
      {isAdmin && <NavLink to="/languages" className={linkClass}>Languages</NavLink>}
      <NavLink to="/audit-log" className={linkClass}>Audit Log</NavLink>
      {isAdmin && <NavLink to="/mappings" className={linkClass}>Mappings</NavLink>}
      <NavLink to="/stats" className={linkClass}>Stats</NavLink>
      <div className="ml-auto">
        <button
          onClick={handleLogout}
          className="flex items-center gap-1 text-slate-400 hover:text-white text-sm"
        >
          <LogOut size={16} />
          Sign out
        </button>
      </div>
    </nav>
  );
}
