package notify

import "time"

// timeAfter is a seam so tests can run without real sleeps.
var timeAfter = time.After
