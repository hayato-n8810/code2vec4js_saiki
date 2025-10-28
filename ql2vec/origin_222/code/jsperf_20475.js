function FUNCTION_1(VAR_1, VAR_2) {
  var VAR_3;
  for (VAR_3 in VAR_2) {
    if (VAR_2.hasOwnProperty(VAR_3)) {
      if (!VAR_1[VAR_3]) {
        VAR_1[VAR_4] = VAR_2[VAR_3];
      }
    }
  }
}
FUNCTION_1({}, {});
