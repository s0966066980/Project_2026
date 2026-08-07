// @ts-check

/**
 * One authority for every UI label that means "order as guest".
 * The UI resolves into menu startup only after `chooseGuest` accepts the choice.
 *
 * `chooseGuest` is mandatory: a caller that forgets to wire it must fail visibly
 * rather than drop the customer into the menu without the decision being made.
 *
 * @param {{
 *   chooseGuest?: () => Promise<unknown> | unknown,
 *   onAccepted: () => void,
 *   onRejected?: (error: unknown) => void,
 * }} options
 */
export async function completeGuestOrderingChoice({ chooseGuest, onAccepted, onRejected }) {
  try {
    if (typeof chooseGuest !== 'function') throw new Error('guest_ordering_choice_unwired');
    await chooseGuest();
    onAccepted();
    return true;
  } catch (error) {
    onRejected?.(error);
    return false;
  }
}
