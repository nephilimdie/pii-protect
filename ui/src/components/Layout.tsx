import { Outlet } from "react-router-dom";
import { NavBar } from "./NavBar";

interface LayoutProps {
  isAdmin: boolean;
}

export function Layout({ isAdmin }: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar isAdmin={isAdmin} />
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
