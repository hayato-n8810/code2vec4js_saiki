function FUNCTION_1(VAR_1, VAR_2) {
  return Math.floor(Math.random() * (VAR_2 - VAR_1 + 1)) + VAR_1;
}
var VAR_3 = [];
for (VAR_4 = 0; VAR_4 < 1000; VAR_4++) VAR_3.push(FUNCTION_1(0, 1000));
var VAR_5 = 0;
for (k in VAR_3) if (VAR_3.hasOwnProperty(k)) VAR_5 += VAR_3[k];
console.log(VAR_5);
