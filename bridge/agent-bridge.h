/* The agent bridge: the Borg's hands and eyes, given to an outside process.
 *
 * Applied to the pinned game tree the way the zoo's observer is (see
 * src/borg_agent/build.py). It adds a connection and changes no rule of the
 * game and no decision of the Borg: with the agent mode off, every function
 * here returns at once and play is byte-identical to the unpatched build
 * (RULES 9).
 *
 * Same licensing as the files it is built with; never part of the ordinary
 * product.
 */
#ifndef AGENT_BRIDGE_H
#define AGENT_BRIDGE_H

/* Included at the top of borg.c, before angband.h. */
#include <stdbool.h>

/* True when BORG_AGENT_OBS and BORG_AGENT_ACT name the two pipes. */
bool agent_active(void);

/* One decision: write an observation, wait for one action, queue its keys.
 * Called where the Borg would think; the game waits for the agent (R1.3). */
void agent_think(void);

#endif
