var VAR_1 = {};
function FUNCTION_1(VAR_2) {
  for (var VAR_3 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_3)) return false;
  }
  return true;
}
FUNCTION_1(VAR_1);
