import { i18nProvider } from "fumadocs-ui/i18n";
import { RootProvider } from "fumadocs-ui/provider/next";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { translations } from "@/lib/layout.shared";
import "./global.css";

export const metadata: Metadata = {
	title: { template: "%s · Puente docs", default: "Puente · Docs internas" },
	description:
		"Documentación interna del equipo 09 (Hackathon FISC 2026, Reto 3).",
};

export default function Layout({ children }: { children: ReactNode }) {
	return (
		<html lang="es" suppressHydrationWarning>
			<body className="flex min-h-screen flex-col">
				<RootProvider i18n={i18nProvider(translations)}>
					{children}
				</RootProvider>
			</body>
		</html>
	);
}
