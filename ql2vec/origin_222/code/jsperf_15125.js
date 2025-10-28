var VAR_1 = new Object();
VAR_1["firstname"] = "Gareth";
VAR_1["lastname"] = "Simpson";
VAR_1["nickname"] = "Ohoboho";
VAR_1["age"] = 21;
function FUNCTION_1() {
  var VAR_2 = 0,
    VAR_3;
  for (VAR_3 in VAR_1) {
    VAR_2++;
  }
  return VAR_2;
}
function FUNCTION_2() {
  var VAR_4 = 0,
    VAR_5;
  for (VAR_5 in VAR_1) {
    if (VAR_1.hasOwnProperty(VAR_5)) {
      VAR_4++;
    }
  }
  return VAR_4;
}
var VAR_6 = 0;
VAR_6 = FUNCTION_2();
