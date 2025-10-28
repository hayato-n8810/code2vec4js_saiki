var VAR_1 = {};
var FUNCTION_1 = function (VAR_2) {
  for (var VAR_3 in VAR_2) {
    if (VAR_2.hasOwnProperty(VAR_3)) delete VAR_2[VAR_3];
  }
};
FUNCTION_1(VAR_1);
VAR_1.VAR_4 = "A";
VAR_1.VAR_5 = "Hello!";
VAR_1.VAR_6 = "Goodbye!";
