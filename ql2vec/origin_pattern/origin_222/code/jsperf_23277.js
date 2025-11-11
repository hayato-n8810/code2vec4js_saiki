var VAR_1 = {
  KEY_1: 1,
  KEY_2: 2,
  KEY_3: 3,
};
function FUNCTION_1(VAR_2) {
  var VAR_3 = 0;
  for (var VAR_4 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_4)) {
      VAR_3 += parseFloat(VAR_1[VAR_4]);
    }
  }
  return VAR_3;
}
FUNCTION_1(VAR_1);
