Object.prototype.VAR_1 = "hi";
var VAR_2 = {};
var VAR_3 = true;
function FUNCTION_1(VAR_4) {
  for (var VAR_5 in VAR_2) {
    return false;
  }
  return true;
}
function FUNCTION_2(VAR_6) {
  for (var VAR_7 in VAR_2) {
    if (VAR_2.hasOwnProperty(VAR_7)) return false;
  }
  return true;
}
FUNCTION_2(VAR_2);
