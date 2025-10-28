var VAR_1 = [
  {
    KEY_1: "black",
    KEY_2: "sedan",
    KEY_3: "auto",
    KEY_4: "petrol",
  },
  {
    KEY_5: "blue",
    KEY_6: "pickup",
    KEY_7: "manual",
    KEY_8: "diesel",
  },
  {},
];
function FUNCTION_1(VAR_2) {
  if (VAR_2) {
    for (var VAR_3 in VAR_2) {
      return false;
      if (VAR_2.hasOwnProperty(VAR_3)) {
        return false;
      }
    }
  }
  return true;
}
function FUNCTION_2(VAR_4) {
  return Object.keys(VAR_4).length > 0;
}
VAR_1.forEach(function (VAR_5) {
  return FUNCTION_1(VAR_5);
});
