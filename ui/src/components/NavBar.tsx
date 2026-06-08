import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { LogOut, ShieldCheck, ChevronDown } from "lucide-react";
import { clearKey } from "../lib/auth";

interface NavBarProps {
  isAdmin: boolean;
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 rounded text-sm font-medium transition-colors ${
    isActive ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"
  }`;

interface DropdownItem {
  to: string;
  label: string;
}

interface NavDropdownProps {
  label: string;
  items: DropdownItem[];
  activePaths: string[];
}

function NavDropdown({ label, items, activePaths }: NavDropdownProps) {
  const location = useLocation();
  const isGroupActive = activePaths.some(p => location.pathname.startsWith(p));

  return (
    <div className="relative group">
      <button
        className={`flex items-center gap-1 px-3 py-2 rounded text-sm font-medium transition-colors ${
          isGroupActive ? "bg-slate-700 text-white" : "text-slate-400 hover:text-white"
        }`}
      >
        {label}
        <ChevronDown size={13} className="opacity-60 group-hover:opacity-100 transition-transform group-hover:rotate-180" />
      </button>

      <div className="absolute left-0 top-full pt-1 z-50 hidden group-hover:block">
        <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 min-w-[160px]">
          {items.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block px-4 py-2 text-sm transition-colors ${
                  isActive ? "text-white bg-slate-700" : "text-slate-400 hover:text-white hover:bg-slate-700/50"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      </div>
    </div>
  );
}

export function NavBar({ isAdmin }: NavBarProps) {
  const navigate = useNavigate();

  function handleLogout() {
    clearKey();
    navigate("/login");
  }

  return (
    <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center gap-1">
      <ShieldCheck className="text-indigo-400 mr-2" size={20} />
      <span className="font-semibold text-white mr-4">pii-protect</span>

      <NavLink to="/dashboard" className={linkClass}>Dashboard</NavLink>

      {isAdmin && (
        <NavDropdown
          label="Detection"
          activePaths={["/regex-patterns", "/denylist", "/context-words", "/reclassification"]}
          items={[
            { to: "/regex-patterns", label: "Regex Patterns" },
            { to: "/denylist",       label: "Denylist" },
            { to: "/context-words",  label: "Context Words" },
            { to: "/reclassification", label: "Reclass. Rules" },
          ]}
        />
      )}

      {isAdmin && (
        <NavDropdown
          label="Policy"
          activePaths={["/pii-types", "/domain-policies", "/context-types"]}
          items={[
            { to: "/pii-types",       label: "PII Types" },
            { to: "/domain-policies", label: "Domain Policies" },
            { to: "/context-types",   label: "Context Types" },
          ]}
        />
      )}

      {isAdmin && (
        <NavDropdown
          label="System"
          activePaths={["/api-keys", "/languages", "/mappings"]}
          items={[
            { to: "/api-keys",   label: "API Keys" },
            { to: "/languages",  label: "Languages" },
            { to: "/mappings",   label: "Mappings" },
          ]}
        />
      )}

      <NavLink to="/audit-log" className={linkClass}>Audit Log</NavLink>
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
