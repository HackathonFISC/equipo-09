/** Recuerda en este navegador el último perfil de joven creado (comodidad de demo, no autenticación). */
const KEY = "puente:youthId";

export function rememberYouth(id: string) {
	try {
		localStorage.setItem(KEY, id);
	} catch {
		// Almacenamiento bloqueado: el enlace con ?id= sigue funcionando.
	}
}

export function recallYouth(): string | null {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

export function forgetYouth() {
	try {
		localStorage.removeItem(KEY);
	} catch {
		// Nada que limpiar.
	}
}
