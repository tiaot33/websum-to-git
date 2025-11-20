## ADDED Requirements
### Requirement: Accept HTML URL and GitHub target
The tgbot SHALL expose a command that accepts a single HTTP(S) URL pointing to an HTML page and a GitHub repository target in the form `owner/repo` with an optional branch, defining where to store the summary document in the repository root.

#### Scenario: Valid request acknowledged
- **WHEN** the user invokes the command with a valid HTTP(S) URL and repository target
- **THEN** the bot validates the inputs and acknowledges that summarization has started

### Requirement: Summarize HTML content into Markdown with YAML frontmatter
The system SHALL fetch the provided HTML page, extract the meaningful text content, and generate a concise Markdown document using an external LLM without imposing a hard length limit. The document SHALL begin with YAML frontmatter capturing title (if available), source URL, creation timestamp, tags, categories, and keywords, followed by reorganized content that retains useful information, images, and links for readability.

#### Scenario: HTML fetched and summarized
- **WHEN** the HTML page is reachable and content is extracted
- **THEN** the bot produces a Markdown note via external LLM containing YAML frontmatter (title if available, source URL, creation timestamp, tags, categories, keywords) and body sections with key findings

#### Scenario: HTML fetch or parsing fails
- **WHEN** the HTML fetch fails or produces no usable content
- **THEN** the bot returns an error to the user and no summary file is created

#### Scenario: No hard length cap
- **WHEN** the HTML page is lengthy but still processed
- **THEN** the bot returns a summary without rejecting or truncating due to a fixed length limit

#### Scenario: Images and links retained
- **WHEN** the HTML contains images or hyperlinks
- **THEN** the bot preserves them in the Markdown output (as image/anchor references) while reorganizing content

### Requirement: Commit summary to specified GitHub repository root
The system SHALL create a new Markdown file in the specified repository root using a unique deterministic filename (e.g., `summary-<yyyyMMddHHmm>-<slug>.md`) unless the user supplies a filename, containing the generated summary, commit it to the specified branch (defaulting to a configured branch when unspecified), allow overriding commit author, and return the file path or commit link to the user.

#### Scenario: Commit succeeds
- **WHEN** the summary is generated and GitHub credentials authorize pushes to the target branch
- **THEN** the bot writes the file to the repository root, creates a commit with a message referencing the source URL, and responds with the file path or commit link

#### Scenario: Commit fails
- **WHEN** GitHub write fails due to authentication, permissions, or branch issues
- **THEN** the bot reports the failure to the user and retains the summary content for retry without publishing to GitHub

#### Scenario: Custom filename and author accepted
- **WHEN** the user provides a custom filename and/or commit author
- **THEN** the bot uses the provided filename and author while committing the summary to the target branch
