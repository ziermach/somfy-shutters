// Feature 005: the "Rolladen hinzufügen" guide, as data — every word here is tested.
//
// The app never programs a motor or creates a shutter in the bridge (constitution I):
// the person does that in Pi-Somfy's own interface. The guide says what to do there,
// on the remote and at the window, and how to tell each step worked. Labels in quotes
// are Pi-Somfy's own, as its interface shows them.

export type Route = 'remote' | 'power';
export type Where = 'App' | 'Funkbrücke' | 'Fernbedienung' | 'Fenster' | 'Sicherung';

export interface Step {
  id: 'create' | 'learn' | 'power' | 'program' | 'restart' | 'wait';
  where: Where;
  title: string;
  text: string;
  /** How to tell it worked. */
  success: string;
}

/** After this long without a new shutter the guide lists what usually went wrong (FR-010). */
export const TIMEOUT_MS = 10 * 60 * 1000;

const CREATE: Step = {
  id: 'create',
  where: 'Funkbrücke',
  title: 'Rolladen in Pi-Somfy anlegen',
  text: 'Öffne Pi-Somfy, wähle „Add shutter“, gib einen Namen ein und speichere.',
  success: 'Der Rolladen steht in Pi-Somfys Liste.'
};

const LEARN: Step = {
  id: 'learn',
  where: 'Fernbedienung',
  title: 'Motor in den Anlernmodus bringen',
  text: 'Geh ans Fenster. Halte die PROG-Taste auf der Rückseite der alten Fernbedienung gedrückt, bis der Rolladen kurz auf und ab fährt — etwa drei Sekunden.',
  success: 'Der Rolladen wackelt kurz.'
};

const POWER: Step = {
  id: 'power',
  where: 'Sicherung',
  title: 'Strom aus und wieder an',
  text: 'Schalte die Sicherung dieses Motors mindestens 5 Sekunden aus und dann wieder ein. Danach ist der Motor etwa zwei Minuten lang lernbereit.',
  success: 'Der Rolladen fährt nach dem Einschalten kurz an.'
};

const PROGRAM: Step = {
  id: 'program',
  where: 'Funkbrücke',
  title: '„Program“ drücken',
  text: 'Drücke in Pi-Somfy bei diesem Rolladen „Program“ — innerhalb von etwa zwei Minuten nach dem vorigen Schritt.',
  success: 'Der Rolladen wackelt noch einmal: Er hat die Funkbrücke gelernt.'
};

const RESTART: Step = {
  id: 'restart',
  where: 'Funkbrücke',
  title: 'Pi-Somfy neu starten',
  text: 'Starte Pi-Somfy neu. Erst dann meldet es den neuen Rolladen und nimmt Befehle für ihn an.',
  success: 'Pi-Somfy ist wieder erreichbar.'
};

const WAIT: Step = {
  id: 'wait',
  where: 'App',
  title: 'Warten',
  text: 'Sobald Pi-Somfy den neuen Rolladen meldet, geht es hier von selbst weiter.',
  success: '„Neuer Rolladen gefunden“ erscheint.'
};

export function steps(route: Route): Step[] {
  return [CREATE, route === 'power' ? POWER : LEARN, PROGRAM, RESTART, WAIT];
}

/** Shown prominently on the power route (FR-011, US5 scenario 2). */
export const POWER_WARNING =
  'Alle Motoren am selben Stromkreis gehen gleichzeitig in den Anlernmodus und würden denselben Sender lernen. Trenne die anderen Rolladen an dieser Sicherung vorher vom Strom, oder nimm diesen Weg nur, wenn der Motor allein an der Sicherung hängt.';

/** What usually went wrong, most likely first (FR-010, US2 scenario 4). */
export const TIMEOUT_HINTS: string[] = [
  'Pi-Somfy wurde nach dem Anlegen nicht neu gestartet — ohne Neustart meldet es den Rolladen nicht.',
  'Die PROG-Taste wurde nicht lange genug gehalten: Der Rolladen muss kurz gewackelt haben.',
  'Der Anlernmodus ist abgelaufen: „Program“ muss innerhalb von etwa zwei Minuten folgen. Dann noch einmal von vorn.',
  'In Pi-Somfy sind die Ankündigungen ausgeschaltet (EnableDiscovery). Dann meldet es gar keinen Rolladen.'
];

/** The bridge has never announced anything: most likely announcements are off. */
export const NO_ANNOUNCEMENTS_HINT =
  'Pi-Somfy hat noch nie einen Rolladen gemeldet. Wahrscheinlich sind die Ankündigungen ausgeschaltet (EnableDiscovery in Pi-Somfys Einstellungen).';

/** Old announcements of long-deleted shutters come back as "new"; they can be set aside. */
export const STALE_HINT =
  'Taucht ein Rolladen auf, den es längst nicht mehr gibt? Pi-Somfy zieht die Meldung gelöschter Rolladen nie zurück. Übernimm ihn und entferne ihn wieder — dann liegt er beiseite und stört nicht mehr.';

/** A name not yet used in the household: "Küche" → "Küche 2". Case-insensitive. */
export function uniqueName(name: string, taken: string[]): string {
  const base = name.trim() || 'Rolladen';
  const used = new Set(taken.map((t) => t.trim().toLocaleLowerCase('de')));
  let candidate = base;
  for (let n = 2; used.has(candidate.toLocaleLowerCase('de')); n++) candidate = `${base} ${n}`;
  return candidate;
}
