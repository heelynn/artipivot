import { Outlet, NavLink } from 'react-router-dom'
import { useTheme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'
import {
  MessageSquare,
  Bot,
  Settings,
  Activity,
  Eye,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeft,
} from 'lucide-react'
import { useState } from 'react'

const navItems = [
  { to: '/', label: 'Chat', icon: MessageSquare },
  { to: '/admin/agents', label: 'Agents', icon: Bot },
  { to: '/admin/config', label: 'Config', icon: Settings },
  { to: '/admin/observe', label: 'Observe', icon: Activity },
  { to: '/admin/runtime', label: 'Runtime', icon: Eye },
]

export function AppLayout() {
  const { theme, toggleTheme } = useTheme()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside
        className={cn(
          'flex flex-col border-r border-sidebar-border bg-sidebar-background transition-all duration-200',
          collapsed ? 'w-16' : 'w-60'
        )}
      >
        {/* Logo area */}
        <div className="flex h-14 items-center justify-between border-b border-sidebar-border px-4">
          {!collapsed && (
            <span className="text-lg font-semibold text-sidebar-foreground">
              ArtiPivot
            </span>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="rounded-md p-1.5 text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-foreground font-medium'
                    : 'text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground'
                )
              }
            >
              <Icon size={18} />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Bottom controls */}
        <div className="border-t border-sidebar-border p-2">
          <button
            onClick={toggleTheme}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground"
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            {!collapsed && <span>{theme === 'dark' ? 'Light' : 'Dark'}</span>}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
