var VAR_1 = {},
  VAR_2 = {
    KEY_1: "val1",
    KEY_2: "val2",
    KEY_3: "val3",
    KEY_4: "val4",
    KEY_5: "val5",
    KEY_6: "val6",
    KEY_7: "val7",
    KEY_8: "val8",
    KEY_9: "val9",
    KEY_10: "val10",
  };
function FUNCTION_1(VAR_3) {
  for (var VAR_4 in VAR_3) {
    if (VAR_3.hasOwnProperty(VAR_4)) {
      return false;
    }
  }
  return true;
}
function FUNCTION_2(VAR_5) {
  for (var VAR_6 in VAR_5) {
    return false;
  }
  return true;
}
FUNCTION_1(VAR_1);
FUNCTION_1(VAR_2);
