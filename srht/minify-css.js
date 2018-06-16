var purify = require('purify-css');

var input = process.argv[2];
var output = process.argv[3];
var files = [];

for (var i = 4; i < process.argv.length; ++i) {
  files.push(process.argv[i]);
}

purify(files, [input], {
  minify: true,
  output: output,
  whitelist: ["*cgit*", "*fa-*"],
});
