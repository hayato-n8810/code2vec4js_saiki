var VAR_1 = 0,
  VAR_2 = "q",
  VAR_3 = ["1", 2, "3", 4, "5", "6", 7],
  VAR_4 = {
    KEY_1: "1",
    KEY_2: 2,
    KEY_3: "3",
    KEY_4: 4,
    5: "5",
    KEY_5: "6",
    KEY_6: 7,
  };
for (i in VAR_4) {
  if (VAR_4.hasOwnProperty(i) && VAR_2 === i) {
    VAR_1 = VAR_4[i];
  }
}
