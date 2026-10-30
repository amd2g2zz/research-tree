/** Ledger boundary error — shared by the event log, the surface CRUD and the
 * schema validators (kept in its own module so the validator can throw the
 * canonical type without a circular import). */

export class LedgerIntegrityError extends Error {}
