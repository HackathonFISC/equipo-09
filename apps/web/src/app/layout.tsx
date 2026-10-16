import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import "../index.css";
import Header from "@/components/header";
import Providers from "@/components/providers";

const inter = Inter({
	variable: "--font-inter",
	subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
	variable: "--font-jetbrains-mono",
	subsets: ["latin"],
});

export const metadata: Metadata = {
	title: { default: "Puente", template: "%s · Puente" },
	description:
		"Inserción laboral juvenil en Panamá: agentes que conectan jóvenes, empresas y centros de formación, con un orientador humano en cada decisión.",
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="es" suppressHydrationWarning>
			<body
				className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}
			>
				<Providers>
					<div className="flex min-h-svh flex-col">
						<Header />
						<div className="flex flex-1 flex-col">{children}</div>
					</div>
				</Providers>
			</body>
		</html>
	);
}
