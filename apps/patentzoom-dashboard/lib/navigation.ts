import {
  BarChart3,
  Bot,
  FileText,
  Gauge,
  Globe2,
  Home,
  PenSquare,
  Rocket,
  Settings,
  Sparkles,
} from "lucide-react";

export const navigation = [
  { title: "Dashboard", href: "/dashboard", icon: Home },
  { title: "Keywords", href: "/keywords", icon: Sparkles },
  { title: "AI Writer", href: "/writer", icon: PenSquare },
  { title: "Articles", href: "/articles", icon: FileText },
  { title: "Publishing", href: "/publishing", icon: Rocket },
  { title: "Search Console", href: "/search-console", icon: Globe2 },
  { title: "SEO Optimization", href: "/seo-optimization", icon: Gauge },
  { title: "Automations", href: "/automations", icon: Bot },
  { title: "Analytics", href: "/analytics", icon: BarChart3 },
  { title: "Settings", href: "/settings", icon: Settings },
];

