var VAR_1 = "";
var VAR_2 = {
  1: "a",
  2: "b",
  3: "c",
  4: "d",
  5: "e",
  6: "f",
  7: "a",
  8: "b",
  9: "c",
  10: "d",
  11: "e",
  12: "f",
  13: "a",
  14: "b",
  15: "c",
  16: "d",
  17: "e",
  18: "f",
  19: "a",
  20: "b",
  21: "c",
  22: "d",
  23: "e",
  24: "f",
};
for (var VAR_3 in VAR_2) {
  if (!VAR_2.hasOwnProperty(VAR_3)) {
    continue;
  }
  VAR_1 += VAR_2[VAR_3];
}
