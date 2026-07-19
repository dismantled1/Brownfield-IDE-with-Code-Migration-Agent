package backend.models.schemas;

import java.util.List;
import java.util.Optional;

public class FileNode {
    private String name;
    private String path;
    private String type;
    private Optional<String> extension;
    private Optional<Integer> size;
    private Optional<Float> modified;
    private Optional<List<FileNode>> children;

    public FileNode(String name, String path, String type, Optional<String> extension, Optional<Integer> size, Optional<Float> modified, Optional<List<FileNode>> children) {
        this.name = name;
        this.path = path;
        this.type = type;
        this.extension = extension;
        this.size = size;
        this.modified = modified;
        this.children = children;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Optional<String> getExtension() {
        return extension;
    }

    public void setExtension(Optional<String> extension) {
        this.extension = extension;
    }

    public Optional<Integer> getSize() {
        return size;
    }

    public void setSize(Optional<Integer> size) {
        this.size = size;
    }

    public Optional<Float> getModified() {
        return modified;
    }

    public void setModified(Optional<Float> modified) {
        this.modified = modified;
    }

    public Optional<List<FileNode>> getChildren() {
        return children;
    }

    public void setChildren(Optional<List<FileNode>> children) {
        this.children = children;
    }
}

public class FileContent {
    private String path;
    private String content;
    private int size;
    private String encoding;
    private Optional<String> language;

    public FileContent(String path, String content, int size, String encoding, Optional<String> language) {
        this.path = path;
        this.content = content;
        this.size = size;
        this.encoding = encoding;
        this.language = language;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public int getSize() {
        return size;
    }

    public void setSize(int size) {
        this.size = size;
    }

    public String getEncoding() {
        return encoding;
    }

    public void setEncoding(String encoding) {
        this.encoding = encoding;
    }

    public Optional<String> getLanguage() {
        return language;
    }

    public void setLanguage(Optional<String> language) {
        this.language = language;
    }
}

public class WriteFileRequest {
    private String path;
    private String content;

    public WriteFileRequest(String path, String content) {
        this.path = path;
        this.content = content;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }
}

public class CreateFileRequest {
    private String path;

    public CreateFileRequest(String path) {
        this.path = path;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }
}

public class CreateFolderRequest {
    private String path;

    public CreateFolderRequest(String path) {
        this.path = path;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }
}

public class DeleteRequest {
    private String path;

    public DeleteRequest(String path) {
        this.path = path;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }
}

public class RenameRequest {
    private String path;
    private String newName;

    public RenameRequest(String path, String newName) {
        this.path = path;
        this.newName = newName;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getNewName() {
        return newName;
    }

    public void setNewName(String newName) {
        this.newName = newName;
    }
}

public class SearchResult {
    private List<FileNode> nodes;
    private int total;
    private String query;

    public SearchResult(List<FileNode> nodes, int total, String query) {
        this.nodes = nodes;
        this.total = total;
        this.query = query;
    }

    public List<FileNode> getNodes() {
        return nodes;
    }

    public void setNodes(List<FileNode> nodes) {
        this.nodes = nodes;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }

    public String getQuery() {
        return query;
    }

    public void setQuery(String query) {
        this.query = query;
    }
}

public class RecentProject {
    private String path;
    private String name;
    private String openedAt;

    public RecentProject(String path, String name, String openedAt) {
        this.path = path;
        this.name = name;
        this.openedAt = openedAt;
    }

    public String getPath() {
        return path;
    }

    public void setPath(String path) {
        this.path = path;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getOpenedAt() {
        return openedAt;
    }

    public void setOpenedAt(String openedAt) {
        this.openedAt = openedAt;
    }
}

public class WorkspaceState {
    private Optional<String> path;
    private List<RecentProject> recentProjects;

    public WorkspaceState(Optional<String> path, List<RecentProject> recentProjects) {
        this.path = path;
        this.recentProjects = recentProjects;
    }

    public Optional<String> getPath() {
        return path;
    }

    public void setPath(Optional<String> path) {
        this.path = path;
    }

    public List<RecentProject> getRecentProjects() {
        return recentProjects;
    }

    public void setRecentProjects(List<RecentProject> recentProjects) {
        this.recentProjects = recentProjects;
    }
}

public class TerminalOutput {
    private String command;
    private String output;

    public TerminalOutput(String command, String output) {
        this.command = command;
        this.output = output;
    }

    public String getCommand() {
        return command;
    }

    public void setCommand(String command) {
        this.command = command;
    }

    public String getOutput() {
        return output;
    }

    public void setOutput(String output) {
        this.output = output;
    }
}

public class TerminalInput {
    private String input;

    public TerminalInput(String input) {
        this.input = input;
    }

    public String getInput() {
        return input;
    }

    public void setInput(String input) {
        this.input = input;
    }
}
