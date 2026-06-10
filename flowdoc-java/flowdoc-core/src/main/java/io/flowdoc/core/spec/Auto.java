package io.flowdoc.core.spec;

import java.util.List;

/** Information the parser extracted automatically from code structure. */
public record Auto(
        List<Param> params,
        Returns returns,
        List<AnnotationInfo> annotations
) {
}
