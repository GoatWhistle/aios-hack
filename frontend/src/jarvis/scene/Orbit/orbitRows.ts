export interface OrbitSeatShape {
  wide: boolean;
  open: boolean;
}

export const fullRowSeats = (seats: readonly OrbitSeatShape[]): boolean[] => {
  const full = seats.map((seat) => seat.wide || seat.open);
  let column = 0;
  seats.forEach((_, index) => {
    if (full[index]) {
      column = 0;
      return;
    }
    const next = seats[index + 1];
    const nextTakesRow = next === undefined || next.wide || next.open;
    if (column === 0 && nextTakesRow) {
      full[index] = true;
      return;
    }
    column = column === 0 ? 1 : 0;
  });
  return full;
};
